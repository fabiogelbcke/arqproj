"""Reading an office's details."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.office.models import OfficeProfile
from backend.tenancy.resolve import CurrentTenant


async def profile(db: AsyncSession) -> OfficeProfile | None:
    """This office's details (the session is scoped to it), if set."""
    return await db.scalar(select(OfficeProfile))


async def display_name(db: AsyncSession, tenant: CurrentTenant) -> str:
    """The name the office chose, or the registry's until it chooses one."""
    found = await profile(db)
    return found.display_name if found else tenant.name
