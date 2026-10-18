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


def logo_urls(found: OfficeProfile | None) -> tuple[str | None, str | None]:
    """The logo's address and the dark mode logo's (None: the logo shows in dark
    mode too). Each changes when the office's details do, so browsers fetch the
    new one; microseconds, so two changes within a second still differ."""
    if found is None or found.logo_file_id is None:
        return None, None
    version = f"{found.updated_at.timestamp():.6f}"
    dark = f"/api/office/logo?dark=true&v={version}" if found.logo_dark_file_id else None
    return f"/api/office/logo?v={version}", dark
