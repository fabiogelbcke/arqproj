"""Public facts about the office at this address: its name and language.

The sign-in and choose-password screens need them before anyone is signed in.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.engine import get_tenant_session
from backend.office.profile import display_name
from backend.tenancy.models import Locale
from backend.tenancy.resolve import CurrentTenant, current_tenant

router = APIRouter(prefix="/api")


class TenantOut(BaseModel):
    name: str
    locale: Locale


@router.get("/tenant")
async def tenant(
    tenant: CurrentTenant = Depends(current_tenant), db: AsyncSession = Depends(get_tenant_session)
) -> TenantOut:
    return TenantOut(name=await display_name(db, tenant), locale=tenant.locale)
