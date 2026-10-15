"""Connection pool and sessions.

The app creates one engine at startup and disposes of it at shutdown (see
`backend.app`). Request handlers get a session through `get_session`, which
closes it when the request ends; a session never outlives its request.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.settings import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    # Small pool: Cloud SQL's smallest instances allow few connections, and every
    # Cloud Run instance has its own pool. Tune from measurements (plan section 4).
    return create_async_engine(
        settings.database_url, pool_size=5, max_overflow=5, pool_pre_ping=True
    )


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request."""
    async with request.app.state.sessionmaker() as session:
        yield session
