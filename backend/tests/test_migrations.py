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

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import CheckConstraint, MetaData, create_engine, inspect, text
from sqlalchemy.engine import make_url

from backend.db import local
from backend.db.registry import metadata
from backend.tests.conftest import TEST_DATABASE_URL, alembic_config


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
