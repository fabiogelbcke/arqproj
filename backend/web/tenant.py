"""Public facts about the office at this address: its name, language and logo.

The sign-in and choose-password screens need them before anyone is signed in
(the logo is public already: client pages show it).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.engine import get_tenant_session
from backend.office.profile import logo_urls
from backend.office.profile import profile as load_profile
from backend.tenancy.models import Locale
from backend.tenancy.resolve import CurrentTenant, current_tenant

router = APIRouter(prefix="/api")


class VisitorAnalyticsOut(BaseModel):
    """PostHog for project pages' visitors (A39): cookieless, no person profiles.
    Only where the server has PostHog set (production)."""

    token: str  # PostHog's project token: public by design, not a secret
    host: str
    tenant_id: uuid.UUID  # the office: PostHog's `tenant` group


class TenantOut(BaseModel):
    name: str
    slug: str
    locale: Locale
    logo_url: str | None
    logo_dark_url: str | None  # None: the logo shows in dark mode too
    analytics: VisitorAnalyticsOut | None


@router.get("/tenant")
async def tenant(
    request: Request,
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> TenantOut:
    found = await load_profile(db)
    logo_url, logo_dark_url = logo_urls(found)
    settings = request.app.state.settings
    analytics = (
        VisitorAnalyticsOut(
            token=settings.posthog_project_token, host=settings.posthog_host, tenant_id=tenant.id
        )
        if settings.posthog_project_token and settings.posthog_host
        else None
    )
    return TenantOut(
        name=found.display_name if found else tenant.name,
        slug=tenant.slug,
        locale=tenant.locale,
        logo_url=logo_url,
        logo_dark_url=logo_dark_url,
        analytics=analytics,
    )
