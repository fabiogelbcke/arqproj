"""Connection pool and sessions.

The app creates one engine at startup and disposes of it at shutdown (see
`backend.app`). Request handlers get a session through `get_session`, which
closes it when the request ends; a session never outlives its request.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.db.isolation import scope_to_tenant
from backend.settings import Settings
from backend.tenancy.resolve import CurrentTenant, current_tenant


def create_engine(settings: Settings) -> AsyncEngine:
    # Small pool: Cloud SQL's smallest instances allow few connections, and every
    # Cloud Run instance has its own pool. Tune from measurements (plan section 4).
    return create_async_engine(
        settings.database_url, pool_size=5, max_overflow=5, pool_pre_ping=True
    )


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, not scoped to any tenant.
    Only for the routing registry; tenant data needs `get_tenant_session`."""
    async with request.app.state.sessionmaker() as session:
        yield session


async def get_tenant_session(
    request: Request, tenant: CurrentTenant = Depends(current_tenant)
) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: a session whose every transaction is for this tenant, so
    row-level security shows and accepts only its rows."""
    async with request.app.state.sessionmaker() as session:
        scope_to_tenant(session.sync_session, tenant.id)
        yield session
