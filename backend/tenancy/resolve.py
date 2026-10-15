"""Which tenant a request is for, decided only by its exact hostname.

The whole hostname is looked up in `tenant_domains`; nothing is parsed out of it
(no "slug from the subdomain"). A product subdomain and a custom domain are both
just rows. The only shape-based rule is `www.`, which maps to the same host
without it.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from backend.tenancy.models import Tenant, TenantDomain

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class CurrentTenant:
    """The tenant a request belongs to: a read-only copy, not a database row, so
    code can neither change it by accident nor trigger hidden queries through it."""

    id: uuid.UUID
    slug: str
    name: str
    locale: str
    timezone: str
    primary_host: str


@dataclass(frozen=True)
class Resolution:
    tenant: Tenant
    # Set when the request must move to another host: an alias, or a `www.` form.
    redirect_host: str | None = None


def normalize_host(raw: str | None) -> str | None:
    """`Alinea.LocalHost:8000.` → `alinea.localhost`. None if there is nothing usable."""
    if not raw:
        return None
    host = raw.strip().lower()
    if host.startswith("["):  # IPv6 literal; never a tenant address
        return None
    host = host.rsplit(":", 1)[0] if ":" in host else host
    host = host.rstrip(".")
    return host or None


async def _lookup(session: AsyncSession, hostname: str) -> tuple[Tenant, str | None] | None:
    """The active tenant owning `hostname`, and that tenant's primary hostname."""
    primary = aliased(TenantDomain)
    row = (
        await session.execute(
            select(Tenant, primary.hostname)
            .join(TenantDomain, TenantDomain.tenant_id == Tenant.id)
            .outerjoin(primary, (primary.tenant_id == Tenant.id) & primary.is_primary)
            .where(TenantDomain.hostname == hostname, Tenant.status == "active")
        )
    ).first()
    return (row[0], row[1]) if row else None


async def resolve(session: AsyncSession, raw_host: str | None) -> Resolution | None:
    """None means "not found": unknown host, suspended tenant, or no usable Host."""
    host = normalize_host(raw_host)
    if host is None:
        return None
    is_www = host.startswith("www.")
    found = await _lookup(session, host.removeprefix("www.") if is_www else host)
    if found is None:
        return None
    row, primary_host = found
    if primary_host is None:
        # Misconfigured tenant (no primary address): serve where it was asked
        # rather than fail, and say so in the logs.
        log.warning("tenant %s has no primary address; serving on %s", row.slug, host)
        primary_host = host.removeprefix("www.")
    tenant = CurrentTenant(
        id=row.id,
        slug=row.slug,
        name=row.name,
        locale=row.locale,
        timezone=row.timezone,
        primary_host=primary_host,
    )
    return Resolution(tenant=tenant, redirect_host=None if host == primary_host else primary_host)


def current_tenant(request: Request) -> CurrentTenant:
    """FastAPI dependency for routes that belong to a tenant.

    The middleware attaches the tenant before routing. A route reaching here
    without one is a programming error (for example an exempt path that asks for
    a tenant), so it fails loudly instead of guessing.
    """
    tenant = getattr(request.state, "tenant", None)
    if tenant is None:
        raise RuntimeError("this route needs a tenant, but none was resolved for the request")
    return tenant
