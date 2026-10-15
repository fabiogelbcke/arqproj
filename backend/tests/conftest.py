"""Shared test setup: a migrated local test database, one rolled-back transaction per test.

The test database is `arqproj_test` on this machine (override with TEST_DATABASE_URL).
Anything that is not a local database is refused, so tests can never touch staging
or production.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import httpx2
import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from backend.app import create_app
from backend.db import local
from backend.db.provision import provision_url
from backend.settings import LOCAL_RUNTIME_ROLE, Settings

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://localhost:5432/arqproj_test"
)
ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"
# Tests set up data as the owner (TEST_DATABASE_URL); isolation tests also connect
# as the app's restricted role, which row-level security applies to.
RUNTIME_ROLE = LOCAL_RUNTIME_ROLE


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
    local.create_runtime_role(RUNTIME_ROLE)
    local.create_database(make_url(TEST_DATABASE_URL).database)
    local.require_local_server_before_use(TEST_DATABASE_URL)  # before any migration
    command.upgrade(alembic_config(TEST_DATABASE_URL), "head")
    provision_url(TEST_DATABASE_URL, RUNTIME_ROLE)
    return TEST_DATABASE_URL


@pytest.fixture
async def db_connection(test_database_url: str) -> AsyncIterator[AsyncConnection]:
    """One connection inside a transaction that is rolled back after the test."""
    engine = create_async_engine(test_database_url, poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        await local.require_local_server(connection)
        try:
            yield connection
        finally:
            await transaction.rollback()
    await engine.dispose()


def _session_on(connection: AsyncConnection) -> AsyncSession:
    # Commits and rollbacks inside a test act on savepoints, so a test can provoke
    # a constraint error, roll back and keep going; nothing ever persists.
    return AsyncSession(
        bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
    )


@pytest.fixture
async def db_session(db_connection: AsyncConnection) -> AsyncIterator[AsyncSession]:
    session = _session_on(db_connection)
    try:
        yield session
    finally:
        await session.close()


@pytest.fixture
def app(db_connection: AsyncConnection) -> FastAPI:
    """The app, with its database sessions on the test's rolled-back connection, so
    requests see exactly the rows the test created."""
    application = create_app(Settings(environment="test", database_url=TEST_DATABASE_URL))
    application.state.sessionmaker = lambda: _session_on(db_connection)
    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx2.AsyncClient]:
    """Calls the app in-process; pass `headers={"host": ...}` to choose the address."""
    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
