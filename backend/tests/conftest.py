"""Shared test setup: a migrated local test database, one rolled-back transaction per test.

The test database is `arqproj_test` on this machine (override with TEST_DATABASE_URL).
Anything that is not a local database is refused, so tests can never touch staging
or production.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from backend.db import local

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://localhost:5432/arqproj_test"
)
ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def alembic_config(database_url: str) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.attributes["database_url"] = database_url
    config.attributes["skip_logging_config"] = True
    return config


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session")
def test_database_url() -> str:
    """Create the test database if needed and bring it to the latest migration."""
    local.require_local(TEST_DATABASE_URL)
    local.create_database(make_url(TEST_DATABASE_URL).database)
    command.upgrade(alembic_config(TEST_DATABASE_URL), "head")
    return TEST_DATABASE_URL


@pytest.fixture
async def db_session(test_database_url: str) -> AsyncIterator[AsyncSession]:
    """A session inside a transaction that is rolled back after the test.

    Commits and rollbacks inside the test act on savepoints, so a test can provoke
    a constraint error, roll back, and keep going; nothing ever persists.
    """
    engine = create_async_engine(test_database_url, poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()
    await engine.dispose()
