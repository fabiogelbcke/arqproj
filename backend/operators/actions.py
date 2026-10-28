"""Tenant lifecycle actions. The caller commits each action and audit together."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text

from backend.db.isolation import scope_to_tenant
from backend.identity import links
from backend.identity.models import JoinLink, Role
from backend.operators.models import OperatorAuditEvent
from backend.tenancy.models import Tenant, TenantDomain, TenantStatus
from backend.web.errors import ApiError, ErrorCode

# Child tables first. Explicit list: a new dependency fails closed until reviewed.
TENANT_TABLES = (
    "share_link_files",
    "proposals",
    "proposal_service_presets",
    "project_events",
    "notification_deliveries",
    "share_links",
    "sessions",
    "project_stages",
    "project_slugs",
    "project_recipients",
    "project_files_seen",
    "project_details",
    "password_links",
    "notification_batches",
    "meetings",
    "join_links",
    "users",
    "tenant_domains",
    "storage_connections",
    "projects",
    "office_profiles",
)


def audit(db, actor: str, action: str, tenant: Tenant, request_id: str) -> None:
    db.add(
        OperatorAuditEvent(
            actor=actor,
            action=action,
            target_tenant_id=tenant.id,
            target_slug=tenant.slug,
            request_id=request_id,
        )
    )


async def owner_link(db, tenant: Tenant, local_port: int = 5173) -> str:
    host = await db.scalar(
        select(TenantDomain.hostname).where(
            TenantDomain.tenant_id == tenant.id, TenantDomain.is_primary
        )
    )
    if host is None or tenant.status is not TenantStatus.ACTIVE:
        raise ApiError(409, ErrorCode.OPERATOR_ACTION_CONFLICT)
    token = secrets.token_urlsafe(32)
    db.add(
        JoinLink(
            tenant_id=tenant.id,
            role=Role.OWNER,
            single_use=True,
            expires_at=datetime.now(UTC) + timedelta(days=7),
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
        )
    )
    url = links.url(host, token, path="/painel/entrar-na-equipe")
    if host.endswith(".localhost"):
        url = url.replace(f":{links.LOCAL_PORT}/", f":{local_port}/", 1)
    return url


async def scoped_tenant(db, slug: str) -> Tenant:
    tenant = await db.scalar(select(Tenant).where(Tenant.slug == slug))
    if tenant is None:
        raise ApiError(404, ErrorCode.PAGE_NOT_FOUND)
    # Start a fresh, scoped transaction, then lock the registry row so two
    # lifecycle actions cannot race each other.
    tenant_id = tenant.id
    await db.close()
    scope_to_tenant(db.sync_session, tenant_id)
    tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_id).with_for_update())
    if tenant is None:
        raise ApiError(404, ErrorCode.PAGE_NOT_FOUND)
    return tenant


async def delete_tenant(db, tenant: Tenant, confirmation: str) -> None:
    if tenant.status is not TenantStatus.SUSPENDED or confirmation != tenant.name:
        raise ApiError(409, ErrorCode.OPERATOR_ACTION_CONFLICT)
    for table in TENANT_TABLES:
        await db.execute(
            text(f'DELETE FROM "{table}" WHERE tenant_id = :tenant'), {"tenant": tenant.id}
        )
    await db.execute(text("DELETE FROM tenants WHERE id = :tenant"), {"tenant": tenant.id})
