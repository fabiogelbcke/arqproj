"""An office as its emails present it: name, language, address, logo, sender.

Apart from the update emails (digest) so the sign-in's password reset email can
use it without loading the web pages' code.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from email.utils import formataddr
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.identity.models import Role, User
from backend.notifications.email import RESEND_TEST_SENDER
from backend.office.models import LogoType, OfficeProfile
from backend.settings import Settings
from backend.tenancy.models import Locale, Tenant, TenantDomain


@dataclass(frozen=True)
class Office:
    name: str
    locale: Locale
    zone: ZoneInfo
    base: str  # where the office's pages are: https://host
    logo_url: str | None
    reply_to: str | None
    sender: str
    staff: frozenset[str]  # its staff accounts' addresses


async def office_of(db: AsyncSession, settings: Settings, tenant_id: uuid.UUID) -> Office:
    tenant = await db.get(Tenant, tenant_id)
    profile = await db.scalar(select(OfficeProfile))
    host = await db.scalar(
        select(TenantDomain.hostname).where(
            TenantDomain.tenant_id == tenant_id, TenantDomain.is_primary
        )
    )
    base = f"https://{host}" if settings.deployed else f"http://{host}:{settings.local_site_port}"
    users = (
        await db.execute(
            select(User.email, User.role).where(User.support.is_(False)).order_by(User.created_at)
        )
    ).all()
    owner = next((email for email, role in users if role is Role.OWNER), None)
    name = profile.display_name if profile else tenant.name
    # Its own domain once verified, else the product's; until either, Resend's
    # test sender (A32).
    domain = settings.email_office_domains.get(tenant.slug) or settings.email_domain
    logo = None
    version = f"v={profile.updated_at.timestamp():.0f}" if profile else ""
    if profile and profile.logo_file_id and profile.logo_type is not LogoType.SVG:
        logo = f"{base}/api/office/logo?{version}"
    elif profile and profile.logo_png_file_id:
        # Gmail and Outlook don't show SVG: the PNG the painel drew of it. Without
        # one yet (an SVG uploaded before PNGs), the office's name in text.
        logo = f"{base}/api/office/logo?png=true&{version}"
    return Office(
        name=name,
        locale=tenant.locale,
        zone=ZoneInfo(tenant.timezone),
        base=base,
        logo_url=logo,
        reply_to=(profile.contact_email if profile else None) or owner,
        sender=formataddr((name, f"atualizacoes@{domain}" if domain else RESEND_TEST_SENDER)),
        staff=frozenset(email for email, _ in users),
    )
