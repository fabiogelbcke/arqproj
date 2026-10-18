"""Alembic environment: runs migrations against MIGRATION_DATABASE_URL (the owner).

Migrations are run as a release step, never at app startup (several instances
starting together must not race to change the schema). Tests pass the URL in
`config.attributes["database_url"]` to point at their own database.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from backend.migrations.registry import MIGRATION_LOCK, metadata
from backend.settings import Settings

config = context.config
if config.config_file_name and not config.attributes.get("skip_logging_config"):
    fileConfig(config.config_file_name, disable_existing_loggers=False)


def _database_url() -> str:
    """Migrations run as the owner role (MIGRATION_DATABASE_URL), never as the app's
    restricted role. Deployed environments must name it explicitly."""
    if config.attributes.get("database_url"):
        return config.attributes["database_url"]
    settings = Settings()
    if settings.deployed and "migration_database_url" not in settings.model_fields_set:
        raise RuntimeError("MIGRATION_DATABASE_URL must be set to run migrations when deployed")
    return settings.migration_database_url


def _configure(connection: Connection) -> None:
    # Overlapping deploys (two merges in quick succession) would otherwise run
    # migrations at the same time; the second waits here until the first is done.
    # Session-level, so it outlives the per-migration transactions and is
    # released when this connection closes.
    connection.exec_driver_sql(f"SELECT pg_advisory_lock({MIGRATION_LOCK})")
    connection.commit()
    context.configure(
        connection=connection,
        target_metadata=metadata,
        compare_type=True,
        # Also compare default values, so autogenerate drafts include default changes.
        # (Check constraints and triggers are never compared by Alembic; the schema
        # tests in backend/tests/test_migrations.py cover those.)
        compare_server_default=True,
        transaction_per_migration=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_online() -> None:
    engine = create_async_engine(_database_url(), poolclass=NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(_configure)
    await engine.dispose()


if context.is_offline_mode():
    context.configure(url=_database_url(), target_metadata=metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(_run_online())
