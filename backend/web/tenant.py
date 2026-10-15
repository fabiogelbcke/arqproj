"""Public facts about the office at this address: its name and language.

The sign-in and choose-password screens need them before anyone is signed in.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.tenancy.models import Locale
from backend.tenancy.resolve import CurrentTenant, current_tenant

router = APIRouter(prefix="/api")


class TenantOut(BaseModel):
    name: str
    locale: Locale


@router.get("/tenant")
async def tenant(tenant: CurrentTenant = Depends(current_tenant)) -> TenantOut:
    return TenantOut(name=tenant.name, locale=tenant.locale)
