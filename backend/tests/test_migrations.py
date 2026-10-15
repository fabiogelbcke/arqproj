"""Migrations apply from empty, undo cleanly, and match the models exactly.

Uses its own throwaway database so going down and up never disturbs other tests.
"""

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from backend.db import local
from backend.db.registry import metadata
from backend.tests.conftest import TEST_DATABASE_URL, alembic_config


@pytest.fixture
def scratch_database_url():
    url = make_url(TEST_DATABASE_URL).set(database="arqproj_test_migrations")
    local.require_local(url.render_as_string(hide_password=False))
    local.drop_database(url.database)
    local.create_database(url.database)
    yield url.render_as_string(hide_password=False)
    local.drop_database(url.database)


def table_names(url: str) -> set[str]:
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            return set(inspect(connection).get_table_names())
    finally:
        engine.dispose()


def test_upgrade_downgrade_upgrade(scratch_database_url):
    config = alembic_config(scratch_database_url)
    command.upgrade(config, "head")
    assert {"tenants", "tenant_domains", "alembic_version"} <= table_names(scratch_database_url)

    command.downgrade(config, "base")
    assert table_names(scratch_database_url) == {"alembic_version"}
    engine = create_engine(scratch_database_url)
    with engine.connect() as connection:
        leftover = connection.scalar(
            text("SELECT count(*) FROM pg_proc WHERE proname = 'set_updated_at'")
        )
    engine.dispose()
    assert leftover == 0

    command.upgrade(config, "head")
    assert {"tenants", "tenant_domains"} <= table_names(scratch_database_url)


def test_migrations_match_the_models(scratch_database_url):
    """A model changed without a migration (or the reverse) fails here."""
    command.upgrade(alembic_config(scratch_database_url), "head")
    engine = create_engine(scratch_database_url)
    with engine.connect() as connection:
        differences = compare_metadata(MigrationContext.configure(connection), metadata)
    engine.dispose()
    assert differences == []
