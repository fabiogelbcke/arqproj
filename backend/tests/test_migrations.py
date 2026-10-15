"""Migrations apply from empty, undo cleanly, and match the models exactly.

"Match exactly" is checked two ways, because Alembic's own comparison does not
cover everything (it ignores check constraints and triggers):

1. Alembic's comparison, with column types and default values enabled.
2. Two real databases, one built by the migrations and one built straight from
   the models, compared through PostgreSQL's own catalog: columns (type,
   nullability, default), every constraint (including check constraints), and
   every index (including partial ones).

Plus a rule the models cannot express: every table with `updated_at` has the
trigger that maintains it.

Each test uses its own throwaway databases, so going down and up never disturbs
other tests.
"""

import getpass
from collections.abc import Iterator

import psycopg
import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import CheckConstraint, MetaData, create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.db import local
from backend.db.isolation import OfficeOwned
from backend.db.provision import app_role_for, provision_url
from backend.db.registry import metadata
from backend.migrations.snippets import (
    CURRENT_TENANT_FUNCTION_SQL,
    POLICY,
    REGISTRY_TABLES,
    enable_office_isolation_sql,
)
from backend.tests.conftest import RUNTIME_ROLE, TEST_DATABASE_URL, alembic_config


def _scratch(name: str) -> Iterator[str]:
    url = make_url(TEST_DATABASE_URL).set(database=name).render_as_string(hide_password=False)
    local.require_local(url)
    local.drop_database(name)
    local.create_database(name)
    local.require_local_server_before_use(url)  # before any migration
    yield url
    local.drop_database(name)


@pytest.fixture
def migrated_url() -> Iterator[str]:
    yield from _scratch("arqproj_test_migrations")


@pytest.fixture
def from_models_url() -> Iterator[str]:
    yield from _scratch("arqproj_test_models")


def _build_from_models(url: str, source: MetaData) -> None:
    engine = create_engine(url)
    with engine.begin() as connection:
        # Office-owned models default tenant_id to this function, so it must exist.
        connection.execute(text(CURRENT_TENANT_FUNCTION_SQL))
        source.create_all(connection)
    engine.dispose()


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
    _build_from_models(from_models_url, metadata)
    assert _differences(schema_snapshot(migrated_url), schema_snapshot(from_models_url)) == {}


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
        # The whole body, whitespace-normalised: an assignment made conditional,
        # unreachable or overwritten would change it.
        function = connection.scalar(
            text(
                "SELECT btrim(regexp_replace(prosrc, '\\s+', ' ', 'g')) "
                "FROM pg_proc WHERE proname = 'set_updated_at'"
            )
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
    assert function == "BEGIN NEW.updated_at = clock_timestamp(); RETURN NEW; END;"


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
    _build_from_models(from_models_url, drifted)
    differences = _differences(schema_snapshot(migrated_url), schema_snapshot(from_models_url))
    assert set(differences) == {"columns", "constraints"}
    assert any("'en'" in str(row) for row in differences["columns"]["only_in_models"])
    assert any("archived" in str(row) for row in differences["constraints"]["only_in_models"])


def _unisolated_office_tables(url: str) -> set[str]:
    """Tables with a tenant_id that lack enforced row-level security, the policy,
    or the default that fills tenant_id with the current office."""
    engine = create_engine(url)
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
                       EXISTS (SELECT 1 FROM pg_policies p
                               WHERE p.tablename = c.relname AND p.policyname = :policy),
                       col.column_default = 'current_tenant_id()'
                FROM pg_class c
                JOIN information_schema.columns col
                  ON col.table_name = c.relname AND col.column_name = 'tenant_id'
                WHERE c.relnamespace = 'public'::regnamespace AND c.relkind = 'r'
                """
            ),
            {"policy": POLICY},
        ).all()
    engine.dispose()
    return {
        name
        for name, enabled, forced, has_policy, has_default in rows
        if name not in REGISTRY_TABLES and not (enabled and forced and has_policy and has_default)
    }


def test_every_office_table_is_isolated(migrated_url):
    """Any future table holding office data must turn on row-level security."""
    command.upgrade(alembic_config(migrated_url), "head")
    assert _unisolated_office_tables(migrated_url) == set()


def test_the_isolation_rule_catches_a_forgotten_table(migrated_url):
    command.upgrade(alembic_config(migrated_url), "head")
    engine = create_engine(migrated_url)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE forgotten (id int, tenant_id uuid)"))
    engine.dispose()
    assert _unisolated_office_tables(migrated_url) == {"forgotten"}


def _grants(url: str, grantee: str) -> set[tuple[str, str]]:
    engine = create_engine(url)
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT table_name, privilege_type FROM information_schema.role_table_grants "
                "WHERE grantee = :grantee"
            ),
            {"grantee": grantee},
        ).all()
    engine.dispose()
    return set(rows)


def test_the_app_group_role_only_reads_the_registry(migrated_url):
    """Privileges belong to the database's group role; the login holds none itself."""
    command.upgrade(alembic_config(migrated_url), "head")
    group = app_role_for(make_url(migrated_url).database)
    assert _grants(migrated_url, group) == {("tenants", "SELECT"), ("tenant_domains", "SELECT")}
    assert _grants(migrated_url, RUNTIME_ROLE) == set()


def test_rotating_the_app_login_moves_access(migrated_url):
    """Changing DATABASE_RUNTIME_ROLE is a re-run of provisioning, not a migration."""
    command.upgrade(alembic_config(migrated_url), "head")
    group = app_role_for(make_url(migrated_url).database)
    rotated = RUNTIME_ROLE + "_rotated"
    local.create_runtime_role(rotated)

    assert provision_url(migrated_url, RUNTIME_ROLE) == [f"{RUNTIME_ROLE} added to {group}"]
    assert provision_url(migrated_url, RUNTIME_ROLE) == []  # repeatable
    assert provision_url(migrated_url, rotated) == [
        f"{rotated} added to {group}",
        f"{RUNTIME_ROLE} removed from {group}",
    ]

    def can_read_registry(login: str) -> bool:
        engine = create_engine(make_url(migrated_url).set(username=login))
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT count(*) FROM tenants"))
            return True
        except ProgrammingError:
            return False
        finally:
            engine.dispose()

    assert can_read_registry(rotated)
    assert not can_read_registry(RUNTIME_ROLE)


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


def test_the_isolation_rule_catches_a_missing_default(migrated_url):
    """Isolated, but tenant_id would have to be set by hand: flagged too."""
    command.upgrade(alembic_config(migrated_url), "head")
    engine = create_engine(migrated_url)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE no_default (id int, tenant_id uuid)"))
        for statement in enable_office_isolation_sql("no_default"):
            connection.execute(text(statement))
        connection.execute(text("ALTER TABLE no_default ALTER COLUMN tenant_id DROP DEFAULT"))
    engine.dispose()
    assert _unisolated_office_tables(migrated_url) == {"no_default"}


def test_office_owned_models_default_to_the_current_office(migrated_url):
    """A model using OfficeOwned builds the same column a migration would."""
    sample = MetaData(naming_convention=metadata.naming_convention)

    class SampleBase(DeclarativeBase):
        metadata = sample

    metadata.tables["tenants"].to_metadata(sample)

    class Sample(OfficeOwned, SampleBase):
        __tablename__ = "sample_office_rows"
        id: Mapped[int] = mapped_column(primary_key=True)

    _build_from_models(migrated_url, sample)
    engine = create_engine(migrated_url)
    with engine.connect() as connection:
        default, nullable = connection.execute(
            text(
                "SELECT column_default, is_nullable FROM information_schema.columns "
                "WHERE table_name = 'sample_office_rows' AND column_name = 'tenant_id'"
            )
        ).one()
    engine.dispose()
    assert (default, nullable) == ("current_tenant_id()", "NO")


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


def _members(url: str, group: str) -> set[str]:
    engine = create_engine(url)
    with engine.connect() as connection:
        rows = connection.scalars(
            text(
                "SELECT m.rolname FROM pg_auth_members a JOIN pg_roles g ON g.oid = a.roleid "
                "JOIN pg_roles m ON m.oid = a.member WHERE g.rolname = :g AND NOT a.admin_option"
            ),
            {"g": group},
        )
        members = set(rows)
    engine.dispose()
    return members


def test_provisioning_refuses_logins_that_bypass_isolation(migrated_url):
    command.upgrade(alembic_config(migrated_url), "head")
    owner = make_url(migrated_url).username or getpass.getuser()  # a superuser locally
    bypass = RUNTIME_ROLE + "_bypass"
    local.create_runtime_role(bypass)
    engine = create_engine(migrated_url)
    with engine.begin() as connection:
        connection.execute(text(f'ALTER ROLE "{bypass}" BYPASSRLS'))
    engine.dispose()

    for login in (owner, bypass):
        with pytest.raises(SystemExit, match="running migrations|bypass row-level security"):
            provision_url(migrated_url, login)
    assert _members(migrated_url, app_role_for(make_url(migrated_url).database)) == set()


def test_a_failed_rotation_changes_nothing(migrated_url, monkeypatch):
    """The new login is never left with access alongside the old one."""
    command.upgrade(alembic_config(migrated_url), "head")
    group = app_role_for(make_url(migrated_url).database)
    rotated = RUNTIME_ROLE + "_rotated"
    local.create_runtime_role(rotated)
    provision_url(migrated_url, RUNTIME_ROLE)

    real_execute = psycopg.Connection.execute

    def fail_on_revoke(self, query, *args, **kwargs):
        if "REVOKE" in str(getattr(query, "as_string", lambda _c: query)(self)):
            raise RuntimeError("interrupted before the old login was removed")
        return real_execute(self, query, *args, **kwargs)

    monkeypatch.setattr(psycopg.Connection, "execute", fail_on_revoke)
    with pytest.raises(RuntimeError, match="interrupted"):
        provision_url(migrated_url, rotated)
    monkeypatch.undo()
    assert _members(migrated_url, group) == {RUNTIME_ROLE}  # the grant was rolled back


def test_provisioning_refuses_a_login_that_owns_tables(migrated_url):
    """Like Cloud SQL's migration login: not a superuser, but owner of the tables,
    so it could alter or drop the isolation policies."""
    command.upgrade(alembic_config(migrated_url), "head")
    owner_like = RUNTIME_ROLE + "_owner"
    local.create_runtime_role(owner_like)
    engine = create_engine(migrated_url)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE owned_by_login (id int)"))
        connection.execute(text(f'ALTER TABLE owned_by_login OWNER TO "{owner_like}"'))
    engine.dispose()
    with pytest.raises(SystemExit, match="owns application tables"):
        provision_url(migrated_url, owner_like)


def test_a_noinherit_login_still_gets_working_access(migrated_url):
    """Membership is granted WITH INHERIT TRUE, whatever the login's own setting."""
    command.upgrade(alembic_config(migrated_url), "head")
    login = RUNTIME_ROLE + "_noinherit"
    local.create_runtime_role(login)
    engine = create_engine(migrated_url)
    with engine.begin() as connection:
        connection.execute(text(f'ALTER ROLE "{login}" NOINHERIT'))
    engine.dispose()
    provision_url(migrated_url, login)

    as_login = create_engine(make_url(migrated_url).set(username=login))
    with as_login.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM tenants")) == 0  # readable
    as_login.dispose()


@pytest.mark.parametrize("power", ["BYPASSRLS", "owns a table"])
def test_provisioning_refuses_a_login_that_can_switch_into_a_powerful_role(migrated_url, power):
    """Checked through the whole membership graph: SET ROLE would hand these over."""
    command.upgrade(alembic_config(migrated_url), "head")
    login = RUNTIME_ROLE + "_member"
    powerful = "arqproj_test_powerful"
    local.create_runtime_role(login)
    engine = create_engine(migrated_url)
    with engine.begin() as connection:
        connection.execute(text(f'DROP ROLE IF EXISTS "{powerful}"'))
        connection.execute(text(f'CREATE ROLE "{powerful}" NOLOGIN'))
        if power == "BYPASSRLS":
            connection.execute(text(f'ALTER ROLE "{powerful}" BYPASSRLS'))
        else:
            connection.execute(text("CREATE TABLE owned_by_role (id int)"))
            connection.execute(text(f'ALTER TABLE owned_by_role OWNER TO "{powerful}"'))
        # Not inherited, only switchable with SET ROLE.
        connection.execute(text(f'GRANT "{powerful}" TO "{login}" WITH INHERIT FALSE, SET TRUE'))
    engine.dispose()
    try:
        with pytest.raises(SystemExit, match=f"could get around office isolation: {powerful}"):
            provision_url(migrated_url, login)
    finally:
        engine = create_engine(migrated_url)
        with engine.begin() as connection:
            connection.execute(text("DROP TABLE IF EXISTS owned_by_role"))
            connection.execute(text(f'DROP ROLE "{powerful}"'))
        engine.dispose()
