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
        # A stage using an old built-in key: 0013 removes those definitions.
        connection.execute(
            text(
                "INSERT INTO project_stages (tenant_id, project_id, position, builtin_key) "
                "VALUES (:t, :p, 1, 'proposal')"
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
            assert connection.scalar(text("SELECT count(*) FROM project_stages")) == 0
    finally:
        with engine.begin() as connection:
            # This throwaway database is dropped after the test anyway.
            connection.execute(text(f'DROP OWNED BY "{owner}"'))
            connection.execute(text(f'DROP ROLE "{owner}"'))
        engine.dispose()


def test_changes_recorded_before_emails_existed_are_never_emailed(migrated_url):
    """0019 closes every existing change into a dropped batch, every office's, even
    as an owner that tenant isolation binds (Cloud SQL's migration login)."""
    from backend.commands import local_db

    owner = RUNTIME_ROLE + "_owner_like_0019"
    local_db.create_runtime_role(owner)
    command.upgrade(alembic_config(migrated_url), "0018")
    engine = create_engine(migrated_url)
    with engine.begin() as connection:
        for slug in ("alinea", "norte"):
            tenant = connection.scalar(
                text("INSERT INTO tenants (slug, name) VALUES (:s, 'X') RETURNING id"), {"s": slug}
            )
            project = connection.scalar(
                text(
                    "INSERT INTO projects (tenant_id, name, client_name, project_type) "
                    "VALUES (:t, 'Casa', 'Cliente', 'architecture') RETURNING id"
                ),
                {"t": tenant},
            )
            connection.execute(
                text(
                    "INSERT INTO project_events (tenant_id, project_id, kind) "
                    "VALUES (:t, :p, 'stage_advanced'), (:t, :p, 'meeting_scheduled')"
                ),
                {"t": tenant, "p": project},
            )
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
            "0019",
        )
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM project_events WHERE batch_id IS NULL")
                )
                == 0
            )
            states = connection.execute(
                text("SELECT state, count(*) FROM notification_batches GROUP BY state")
            ).all()
            assert states == [("dropped", 2)]  # one per project, both offices
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP OWNED BY "{owner}"'))
            connection.execute(text(f'DROP ROLE "{owner}"'))
        engine.dispose()


def test_drafts_are_published_in_every_office(migrated_url):
    """0024 (A35) publishes every office's drafts, and an archived draft comes back
    published if restored, even as an owner that tenant isolation binds (Cloud
    SQL's migration login). Other statuses stay as they were."""
    from backend.commands import local_db

    owner = RUNTIME_ROLE + "_owner_like_0024"
    local_db.create_runtime_role(owner)
    command.upgrade(alembic_config(migrated_url), "0023")
    engine = create_engine(migrated_url)
    with engine.begin() as connection:
        for slug in ("alinea", "norte"):
            tenant = connection.scalar(
                text("INSERT INTO tenants (slug, name) VALUES (:s, 'X') RETURNING id"), {"s": slug}
            )
            connection.execute(
                text(
                    "INSERT INTO projects (tenant_id, name, client_name, project_type, status, "
                    "archived_from) VALUES "
                    "(:t, 'Rascunho', 'C', 'architecture', 'draft', NULL), "
                    "(:t, 'Arquivado', 'C', 'architecture', 'archived', 'draft'), "
                    "(:t, 'Concluido', 'C', 'architecture', 'completed', NULL)"
                ),
                {"t": tenant},
            )
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
            "0024",
        )
        with engine.connect() as connection:
            rows = connection.execute(
                text("SELECT name, status, archived_from FROM projects ORDER BY name")
            ).all()
            assert rows == [
                ("Arquivado", "archived", "active"),
                ("Arquivado", "archived", "active"),
                ("Concluido", "completed", None),
                ("Concluido", "completed", None),
                ("Rascunho", "active", None),
                ("Rascunho", "active", None),
            ]  # both offices
            forced = connection.scalar(
                text("SELECT relforcerowsecurity FROM pg_class WHERE relname = 'projects'")
            )
            assert forced  # isolation is forced again afterwards
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP OWNED BY "{owner}"'))
            connection.execute(text(f'DROP ROLE "{owner}"'))
        engine.dispose()


def test_stage_completion_is_filled_in_every_office(migrated_url):
    """0032 marks as completed the stages before each project's current one, and
    every stage of a completed project (archived since, too), in every office, even as an owner that
    tenant isolation binds (Cloud SQL's migration login)."""
    from backend.commands import local_db

    owner = RUNTIME_ROLE + "_owner_like_0032"
    local_db.create_runtime_role(owner)
    command.upgrade(alembic_config(migrated_url), "0031")
    engine = create_engine(migrated_url)
    with engine.begin() as connection:
        for slug in ("alinea", "norte"):
            tenant = connection.scalar(
                text("INSERT INTO tenants (slug, name) VALUES (:s, 'X') RETURNING id"), {"s": slug}
            )
            for name, status, archived_from, current in (
                ("Ativo", "active", None, 3),
                ("Arquivado", "archived", "completed", 2),
                ("Concluido", "completed", None, 2),
            ):
                project = connection.scalar(
                    text(
                        "INSERT INTO projects (tenant_id, name, client_name, project_type, "
                        "status, archived_from, current_position) "
                        "VALUES (:t, :n, 'C', 'architecture', :s, :a, :c) RETURNING id"
                    ),
                    {"t": tenant, "n": name, "s": status, "a": archived_from, "c": current},
                )
                for position in (1, 2, 3, 4):
                    connection.execute(
                        text(
                            "INSERT INTO project_stages (tenant_id, project_id, position, title) "
                            "VALUES (:t, :p, :n, 'Etapa')"
                        ),
                        {"t": tenant, "p": project, "n": position},
                    )
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
            "0032",
        )
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT p.name, count(*) FILTER (WHERE s.completed_at IS NOT NULL) "
                    "FROM projects p JOIN project_stages s ON s.project_id = p.id "
                    "GROUP BY p.id, p.name ORDER BY p.name"
                )
            ).all()
            # Ativo: stages 1 and 2 (before its current 3); Concluido, and Arquivado
            # (archived when completed, restored completed): all four.
            assert rows == [
                ("Arquivado", 4),
                ("Arquivado", 4),
                ("Ativo", 2),
                ("Ativo", 2),
                ("Concluido", 4),
                ("Concluido", 4),
            ]
            forced = connection.execute(
                text(
                    "SELECT relname, relforcerowsecurity FROM pg_class "
                    "WHERE relname IN ('projects', 'project_stages') ORDER BY relname"
                )
            ).all()
            assert forced == [("project_stages", True), ("projects", True)]  # forced again
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP OWNED BY "{owner}"'))
            connection.execute(text(f'DROP ROLE "{owner}"'))
        engine.dispose()


def test_every_existing_account_starts_confirmed(migrated_url):
    """0035 adds `users.email_confirmed_at`: every account made before it, in every
    office, counts as confirmed (only the shared link makes unconfirmed ones), even
    run as an owner that tenant isolation binds (Cloud SQL's migration login)."""
    from backend.commands import local_db

    owner = RUNTIME_ROLE + "_owner_like_0035"
    local_db.create_runtime_role(owner)
    command.upgrade(alembic_config(migrated_url), "0034")
    engine = create_engine(migrated_url)
    with engine.begin() as connection:
        for slug in ("alinea", "norte"):
            tenant = connection.scalar(
                text("INSERT INTO tenants (slug, name) VALUES (:s, 'X') RETURNING id"), {"s": slug}
            )
            for email, password_hash in (("in@x.example", "hash"), ("invited@x.example", None)):
                connection.execute(
                    text(
                        "INSERT INTO users (tenant_id, email, name, password_hash) "
                        "VALUES (:t, :e, 'Pessoa', :p)"
                    ),
                    {"t": tenant, "e": email, "p": password_hash},
                )
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
            "0035",
        )
        with engine.connect() as connection:
            unconfirmed = connection.scalar(
                text("SELECT count(*) FROM users WHERE email_confirmed_at IS NULL")
            )
            assert connection.scalar(text("SELECT count(*) FROM users")) == 4
            assert unconfirmed == 0
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP OWNED BY "{owner}"'))
            connection.execute(text(f'DROP ROLE "{owner}"'))
        engine.dispose()


def test_existing_join_links_stay_shared_member_links(migrated_url):
    """0037 keeps each office's existing shared link reusable for 24 hours, and
    lets command-created owner links coexist. Migration runs as Cloud SQL's
    non-superuser owner, with forced tenant isolation still in effect."""
    from backend.commands import local_db

    owner = RUNTIME_ROLE + "_owner_like_0037"
    local_db.create_runtime_role(owner)
    command.upgrade(alembic_config(migrated_url), "0036")
    engine = create_engine(migrated_url)
    with engine.begin() as connection:
        for slug in ("alinea", "norte"):
            tenant = connection.scalar(
                text("INSERT INTO tenants (slug, name) VALUES (:s, 'Escritório') RETURNING id"),
                {"s": slug},
            )
            user = connection.scalar(
                text(
                    "INSERT INTO users (tenant_id, email, name, role) "
                    "VALUES (:t, 'ana@x.example', 'Ana', 'owner') RETURNING id"
                ),
                {"t": tenant},
            )
            connection.execute(
                text(
                    "INSERT INTO join_links (tenant_id, created_by, token_hash) VALUES (:t, :u, :h)"
                ),
                {"t": tenant, "u": user, "h": slug},
            )
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
            "head",
        )
        with engine.begin() as connection:
            rows = connection.execute(
                text(
                    "SELECT token_hash FROM join_links WHERE role = 'member' "
                    "AND NOT single_use AND used_at IS NULL AND expires_at IS NULL "
                    "AND revoked_at IS NULL AND created_at > now() - interval '24 hours' "
                    "ORDER BY token_hash"
                )
            ).all()
            assert rows == [("alinea",), ("norte",)]
            # No user is needed for command-created links, and they do not take
            # the shared member link's unique slot.
            connection.execute(
                text(
                    "INSERT INTO join_links (tenant_id, token_hash, role, single_use, expires_at) "
                    "SELECT id, slug || '-owner', 'owner', true, now() + interval '7 days' "
                    "FROM tenants"
                )
            )
            assert connection.scalar(text("SELECT count(*) FROM join_links")) == 4
            assert connection.scalar(
                text("SELECT relforcerowsecurity FROM pg_class WHERE relname = 'join_links'")
            )
        # Downgrading removes owner links before restoring the member-only
        # schema, so both tenants keep their original shared link.
        command.downgrade(
            alembic_config(make_url(migrated_url).set(username=owner).render_as_string(False)),
            "0036",
        )
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT token_hash FROM join_links ORDER BY token_hash")
            ).all() == [("alinea",), ("norte",)]
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP OWNED BY "{owner}"'))
            connection.execute(text(f'DROP ROLE "{owner}"'))
        engine.dispose()


def test_survey_assessment_becomes_survey_in_every_office(migrated_url):
    """0038 replaces "Levantamento e Diagnóstico" with "Levantamento" in every
    office's projects (a project that had both keeps the old one as its own stage),
    even run as an owner that tenant isolation binds (Cloud SQL's migration login)."""
    from backend.commands import local_db

    owner = RUNTIME_ROLE + "_owner_like_0038"
    local_db.create_runtime_role(owner)
    command.upgrade(alembic_config(migrated_url), "0037")
    engine = create_engine(migrated_url)
    with engine.begin() as connection:
        for slug in ("alinea", "norte"):
            tenant = connection.scalar(
                text("INSERT INTO tenants (slug, name) VALUES (:s, 'X') RETURNING id"), {"s": slug}
            )
            for name, keys in (
                ("Reforma", ["survey_assessment"]),
                ("Ambas", ["survey", "survey_assessment"]),
            ):
                project = connection.scalar(
                    text(
                        "INSERT INTO projects (tenant_id, name, client_name, project_type) "
                        "VALUES (:t, :n, 'C', 'renovation') RETURNING id"
                    ),
                    {"t": tenant, "n": name},
                )
                for position, key in enumerate(keys, start=1):
                    connection.execute(
                        text(
                            "INSERT INTO project_stages "
                            "(tenant_id, project_id, position, builtin_key, notes) "
                            "VALUES (:t, :p, :n, :k, 'anotado')"
                        ),
                        {"t": tenant, "p": project, "n": position, "k": key},
                    )
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
            "0038",
        )
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT p.name, s.position, s.builtin_key, s.title, s.notes "
                    "FROM project_stages s JOIN projects p ON p.id = s.project_id "
                    "ORDER BY p.name, s.position"
                )
            ).all()
            assert rows == [
                ("Ambas", 1, "survey", None, "anotado"),
                ("Ambas", 1, "survey", None, "anotado"),
                ("Ambas", 2, None, "Levantamento e Diagnóstico", "anotado"),
                ("Ambas", 2, None, "Levantamento e Diagnóstico", "anotado"),
                ("Reforma", 1, "survey", None, "anotado"),
                ("Reforma", 1, "survey", None, "anotado"),
            ]
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM stage_definitions WHERE key = 'survey_assessment'")
                )
                == 0
            )
            assert connection.execute(
                text(
                    "SELECT stage_key FROM project_type_stages WHERE project_type = 'renovation' "
                    "AND stage_key LIKE 'survey%'"
                )
            ).all() == [("survey",)]
            positions = connection.scalars(
                text("SELECT position FROM stage_definitions ORDER BY position")
            ).all()
            assert positions == list(range(positions[0], positions[0] + 11))  # no gap
            assert connection.scalar(
                text("SELECT relforcerowsecurity FROM pg_class WHERE relname = 'project_stages'")
            )
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP OWNED BY "{owner}"'))
            connection.execute(text(f'DROP ROLE "{owner}"'))
        engine.dispose()


def test_support_accounts_go_on_downgrade_and_what_they_made_stays(migrated_url):
    """0044's downgrade removes Suporte Unio (A43) though it made a share link,
    whose maker becomes unknown rather than blocking the downgrade."""
    command.upgrade(alembic_config(migrated_url), "head")
    engine = create_engine(migrated_url)
    try:
        with engine.begin() as connection:
            tenant = connection.scalar(
                text("INSERT INTO tenants (slug, name) VALUES ('alinea', 'Alinea') RETURNING id")
            )
            support = connection.scalar(
                text(
                    "INSERT INTO users (tenant_id, email, name, role, support) "
                    "VALUES (:t, 'suporte-owner@unio.invalid', 'Suporte Unio', 'owner', true) "
                    "RETURNING id"
                ),
                {"t": tenant},
            )
            project = connection.scalar(
                text(
                    "INSERT INTO projects (tenant_id, name, client_name, project_type) "
                    "SELECT :t, 'Casa', 'Ana', key FROM project_types LIMIT 1 RETURNING id"
                ),
                {"t": tenant},
            )
            connection.execute(
                text(
                    "INSERT INTO share_links (tenant_id, project_id, token_hash, created_by) "
                    "VALUES (:t, :p, 'h', :u)"
                ),
                {"t": tenant, "p": project, "u": support},
            )
        command.downgrade(alembic_config(migrated_url), "0043")
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM users")) == 0
            assert connection.execute(text("SELECT created_by FROM share_links")).all() == [
                (None,)
            ]
    finally:
        command.upgrade(alembic_config(migrated_url), "head")
        engine.dispose()
