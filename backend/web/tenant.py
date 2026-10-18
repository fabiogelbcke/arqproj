"""Public facts about the office at this address: its name, language and logo.

The sign-in and choose-password screens need them before anyone is signed in
(the logo is public already: client pages show it).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.engine import get_tenant_session
from backend.office.profile import logo_urls
from backend.office.profile import profile as load_profile
from backend.tenancy.models import Locale
from backend.tenancy.resolve import CurrentTenant, current_tenant

router = APIRouter(prefix="/api")


class TenantOut(BaseModel):
    name: str
    locale: Locale
    logo_url: str | None
    logo_dark_url: str | None  # None: the logo shows in dark mode too


@router.get("/tenant")
async def tenant(
    tenant: CurrentTenant = Depends(current_tenant), db: AsyncSession = Depends(get_tenant_session)
) -> TenantOut:
    found = await load_profile(db)
    logo_url, logo_dark_url = logo_urls(found)
    return TenantOut(
        name=found.display_name if found else tenant.name,
        locale=tenant.locale,
        logo_url=logo_url,
        logo_dark_url=logo_dark_url,
    )
