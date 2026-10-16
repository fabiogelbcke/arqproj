"""Migrations apply from empty, undo cleanly, and match the models exactly.

"Match exactly" is checked two ways, because Alembic's own comparison ignores check
constraints and triggers: Alembic's comparison (types and defaults), and two real
databases (one migrated, one built from the models) compared through PostgreSQL's
catalog. Each test uses its own throwaway databases.
"""

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import CheckConstraint, MetaData, create_engine, inspect, text
from sqlalchemy.engine import make_url

from backend.commands.provision import app_role_for
from backend.migrations.registry import metadata
from backend.migrations.snippets import (
    CURRENT_TENANT_FUNCTION_SQL,
)
from backend.tests.conftest import (
    RUNTIME_ROLE,
    alembic_config,
    build_from_models,
)


def table_names(url: str) -> set[str]:
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            return set(inspect(connection).get_table_names())
    finally:
        engine.dispose()


def schema_snapshot(url: str) -> dict[str, set[tuple]]:
    """What PostgreSQL itself says the schema is, for tables the models own."""
    tables = sorted(metadata.tables)
    queries = {
        "columns": """
            SELECT table_name, column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = ANY(:tables)""",
        "constraints": """
            SELECT c.conrelid::regclass::text, c.conname, pg_get_constraintdef(c.oid)
            FROM pg_constraint c
            WHERE c.connamespace = 'public'::regnamespace
              AND c.conrelid::regclass::text = ANY(:tables)""",
        "indexes": """
            SELECT tablename, indexname, indexdef
            FROM pg_indexes
            WHERE schemaname = 'public' AND tablename = ANY(:tables)""",
        # Functions the code also defines (CURRENT_TENANT_FUNCTION_SQL): a change made
        # only in a migration, or only in code, shows up here. Whitespace-insensitive.
        "functions": """
            SELECT p.proname, pg_get_function_result(p.oid), p.provolatile, l.lanname,
                   btrim(regexp_replace(p.prosrc, '\\s+', ' ', 'g'))
            FROM pg_proc p JOIN pg_language l ON l.oid = p.prolang
            WHERE p.pronamespace = 'public'::regnamespace
              AND p.proname = 'current_tenant_id'""",
    }
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            return {
                name: {tuple(row) for row in connection.execute(text(query), {"tables": tables})}
                for name, query in queries.items()
            }
    finally:
        engine.dispose()


def _differences(a: dict[str, set[tuple]], b: dict[str, set[tuple]]) -> dict:
    return {
        part: {"only_in_migrations": a[part] - b[part], "only_in_models": b[part] - a[part]}
        for part in a
        if a[part] != b[part]
    }


def test_upgrade_downgrade_upgrade(migrated_url):
    config = alembic_config(migrated_url)
    command.upgrade(config, "head")
    assert {"tenants", "tenant_domains", "alembic_version"} <= table_names(migrated_url)

    command.downgrade(config, "base")
    assert table_names(migrated_url) == {"alembic_version"}
    engine = create_engine(migrated_url)
    with engine.connect() as connection:
        leftover = connection.scalar(
            text("SELECT count(*) FROM pg_proc WHERE proname = 'set_updated_at'")
        )
    engine.dispose()
    assert leftover == 0

    command.upgrade(config, "head")
    assert {"tenants", "tenant_domains"} <= table_names(migrated_url)


def test_alembic_finds_no_difference_including_defaults(migrated_url):
    command.upgrade(alembic_config(migrated_url), "head")
    engine = create_engine(migrated_url)
    with engine.connect() as connection:
        context = MigrationContext.configure(
            connection, opts={"compare_type": True, "compare_server_default": True}
        )
        differences = compare_metadata(context, metadata)
    engine.dispose()
    assert differences == []


def test_database_from_migrations_equals_database_from_models(migrated_url, from_models_url):
    """A model changed without a migration (or the reverse) fails here, including
    check constraints, defaults and partial indexes."""
    command.upgrade(alembic_config(migrated_url), "head")
    build_from_models(from_models_url, metadata)
    assert _differences(schema_snapshot(migrated_url), schema_snapshot(from_models_url)) == {}


def test_the_comparison_catches_model_drift(migrated_url, from_models_url):
    """Self-test: change a copy of the models the way a careless edit would, and
    check the comparison above notices. Otherwise it could silently stop working."""
    drifted = MetaData(naming_convention=metadata.naming_convention)
    for table in metadata.tables.values():
        table.to_metadata(drifted)
    tenants = drifted.tables["tenants"]
    tenants.c.locale.server_default.arg = text("'en'")
    for constraint in tenants.constraints:
        if isinstance(constraint, CheckConstraint) and constraint.name.endswith("status_known"):
            constraint.sqltext = text("status IN ('active', 'suspended', 'archived')")

    command.upgrade(alembic_config(migrated_url), "head")
    build_from_models(from_models_url, drifted)
    differences = _differences(schema_snapshot(migrated_url), schema_snapshot(from_models_url))
    assert set(differences) == {"columns", "constraints"}
    assert any("'en'" in str(row) for row in differences["columns"]["only_in_models"])
    assert any("archived" in str(row) for row in differences["constraints"]["only_in_models"])


# The only acceptable policy on a tenant table. Permissive policies combine with
# OR, so any extra one could widen access; hence exactly this one, nothing else.


def test_the_comparison_catches_a_changed_function(migrated_url, from_models_url):
    """Self-test: current_tenant_id() changed only in code (or only in a migration)."""
    command.upgrade(alembic_config(migrated_url), "head")
    engine = create_engine(from_models_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                CURRENT_TENANT_FUNCTION_SQL.replace("NULLIF(", "NULLIF(btrim(").replace(
                    ", '')", "), '')"
                )
            )
        )
        metadata.create_all(connection)
    engine.dispose()
    differences = _differences(schema_snapshot(migrated_url), schema_snapshot(from_models_url))
    assert set(differences) == {"functions"}


def test_every_updated_at_has_its_trigger(migrated_url):
    """Each table with updated_at has exactly the trigger that maintains it: before
    every UPDATE (any column), for each row. Compared as PostgreSQL's full trigger
    definition, so a narrowed trigger (e.g. `BEFORE UPDATE OF name`) fails."""
    command.upgrade(alembic_config(migrated_url), "head")
    engine = create_engine(migrated_url)
    with engine.connect() as connection:
        with_updated_at = set(
            connection.scalars(
                text(
                    "SELECT table_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND column_name = 'updated_at'"
                )
            )
        )
        triggers = set(
            connection.execute(
                text(
                    "SELECT c.relname, pg_get_triggerdef(t.oid) FROM pg_trigger t "
                    "JOIN pg_class c ON c.oid = t.tgrelid "
                    "WHERE NOT t.tgisinternal AND c.relnamespace = 'public'::regnamespace"
                )
            ).all()
        )
    engine.dispose()
    assert with_updated_at  # the rule is not vacuous
    assert triggers == {
        (
            table,
            f"CREATE TRIGGER {table}_set_updated_at BEFORE UPDATE ON public.{table} "
            "FOR EACH ROW EXECUTE FUNCTION set_updated_at()",
        )
        for table in with_updated_at
    }


def test_downgrade_removes_the_group_role(migrated_url):
    config = alembic_config(migrated_url)
    group = app_role_for(make_url(migrated_url).database)
    command.upgrade(config, "head")
    command.downgrade(config, "0001")
    engine = create_engine(migrated_url)
    with engine.connect() as connection:
        exists = connection.scalar(
            text("SELECT count(*) FROM pg_roles WHERE rolname = :r"), {"r": group}
        )
    engine.dispose()
    assert exists == 0


def test_migrations_wait_for_one_already_running(migrated_url):
    """Overlapping deploys: a second `upgrade` waits instead of colliding."""
    import threading

    from backend.migrations.registry import MIGRATION_LOCK

    engine = create_engine(migrated_url)
    with engine.connect() as holder:
        holder.execute(text(f"SELECT pg_advisory_lock({MIGRATION_LOCK})"))
        done = threading.Event()
        worker = threading.Thread(
            target=lambda: (command.upgrade(alembic_config(migrated_url), "head"), done.set())
        )
        worker.start()
        assert not done.wait(2), "migrated while another run held the lock"
        holder.execute(text(f"SELECT pg_advisory_unlock({MIGRATION_LOCK})"))
        worker.join(30)
    engine.dispose()
    assert done.is_set()


def test_data_migrations_run_as_an_owner_that_isolation_binds(migrated_url):
    """On Cloud SQL the migration login owns the tables but is no superuser, so
    forced tenant isolation applies to it too. A migration updating existing rows
    must still reach every office's rows (0008 backfills detail value types; 0013
    deletes the test projects)."""
    from backend.commands import local_db

    owner = RUNTIME_ROLE + "_owner_like"
    local_db.create_runtime_role(owner)
    command.upgrade(alembic_config(migrated_url), "0007")
    engine = create_engine(migrated_url)
    with engine.begin() as connection:
        tenant = connection.scalar(
            text("INSERT INTO tenants (slug, name) VALUES ('alinea', 'A') RETURNING id")
        )
        project = connection.scalar(
            text(
                "INSERT INTO projects (tenant_id, name, client_name, project_type, stage_template) "
                "VALUES (:t, 'Casa', 'Cliente', 'architecture', 'standard') RETURNING id"
            ),
            {"t": tenant},
        )
        connection.execute(
            text(
                "INSERT INTO project_details (tenant_id, project_id, key, position, value_number) "
                "VALUES (:t, :p, 'site_area', 1, 1240)"
            ),
            {"t": tenant, "p": project},
        )
        # Hand everything to a login like Cloud SQL's migration login.
        connection.execute(
            text(
                f"""
                DO $$
                DECLARE t text;
                BEGIN
                    FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
                        EXECUTE format('ALTER TABLE %I OWNER TO %I', t, '{owner}');
                    END LOOP;
                END $$
                """
            )
        )
        for function in ("current_tenant_id()", "set_updated_at()"):
            connection.execute(text(f'ALTER FUNCTION {function} OWNER TO "{owner}"'))
        connection.execute(text(f'GRANT CREATE ON SCHEMA public TO "{owner}"'))
    try:
        command.upgrade(
            alembic_config(make_url(migrated_url).set(username=owner).render_as_string(False)),
            "0008",
        )
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT value_type FROM project_details")) == "area"
        # 0013 deletes the projects made with the old stages, every office's.
        command.upgrade(
            alembic_config(make_url(migrated_url).set(username=owner).render_as_string(False)),
            "0013",
        )
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM projects")) == 0
            assert connection.scalar(text("SELECT count(*) FROM project_details")) == 0
    finally:
        with engine.begin() as connection:
            # This throwaway database is dropped after the test anyway.
            connection.execute(text(f'DROP OWNED BY "{owner}"'))
            connection.execute(text(f'DROP ROLE "{owner}"'))
        engine.dispose()
