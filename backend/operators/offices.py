"""What the operator dashboard shows of each office (A38): counts and health, never
client content (file names, project texts, clients' names or addresses).

Read office by office with the app's own database login, scoped to each office
in turn as a request would be: the isolation policy stays in force, and no
login that sees every office at once is needed for reading. Fine for a handful
of offices; a few queries each.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.db.isolation import scope_to_tenant
from backend.identity.models import LoginSession, Role, User
from backend.notifications.models import DeliveryStatus, NotificationDelivery
from backend.office.models import OfficeProfile
from backend.projects.enums import ProjectStatus
from backend.projects.models import Meeting, Project, ProjectDetail, ProjectStage
from backend.shares.models import ShareLink
from backend.storage.models import StorageConnection
from backend.tenancy.models import Tenant, TenantDomain
from backend.tenancy.resolve import known_features

RECENT = timedelta(days=30)  # "emails sent" counts this long back


@dataclass
class StaffMember:
    name: str
    email: str
    role: Role
    status: str  # active, invited (no password yet), unconfirmed (email not confirmed)
    last_seen_at: datetime | None


@dataclass
class OfficeSummary:
    id: uuid.UUID
    slug: str
    name: str
    status: str
    created_at: datetime
    hosts: list[str]  # the primary first
    owners: int = 0
    staff: int = 0  # every account, owners included
    pending: int = 0  # invited or unconfirmed
    projects: dict[str, int] = field(default_factory=dict)  # by status
    storage: str = "none"  # none, folder (local), google
    writer_status: str | None = None
    reader_status: str | None = None
    drive_account: str | None = None  # the office's Google account (staff's, not a client's)
    last_activity_at: datetime | None = None  # a staff session last used
    emails_sent: int = 0  # client update emails, in the last RECENT
    share_links: int = 0
    downloads: int = 0
    usage: dict[str, int] = field(default_factory=dict)
    link_statuses: dict[str, int] = field(default_factory=dict)
    project_types: dict[str, int] = field(default_factory=dict)
    features: list[str] = field(default_factory=list)  # switched on (A40)
    team: list[StaffMember] = field(default_factory=list)  # only for one office's page


async def _tenants(session: AsyncSession) -> list[tuple[Tenant, list[str]]]:
    """Every office, oldest first, with its addresses (the primary first). The
    registry tables are readable without an office (plan section 4)."""
    tenants = list(await session.scalars(select(Tenant).order_by(Tenant.created_at)))
    rows = (
        await session.execute(
            select(TenantDomain.tenant_id, TenantDomain.hostname, TenantDomain.is_primary)
        )
    ).all()
    hosts: dict[uuid.UUID, list[tuple[bool, str]]] = {}
    for tenant_id, hostname, primary in rows:
        hosts.setdefault(tenant_id, []).append((not primary, hostname))
    return [(t, [h for _, h in sorted(hosts.get(t.id, []))]) for t in tenants]


async def _fill(session: AsyncSession, office: OfficeSummary, now: datetime, team: bool) -> None:
    """Counts for one office; `session` is scoped to it."""
    # Not Suporte Unio (A43): the office's own people and their activity.
    users = list(await session.scalars(select(User).where(User.support.is_(False))))
    office.staff = len(users)
    office.owners = sum(1 for u in users if u.role is Role.OWNER)
    office.pending = sum(
        1 for u in users if u.password_hash is None or u.email_confirmed_at is None
    )
    seen = dict(
        (
            await session.execute(
                select(LoginSession.user_id, func.max(LoginSession.last_seen_at))
                .join(User, User.id == LoginSession.user_id)
                .where(User.support.is_(False))
                .group_by(LoginSession.user_id)
            )
        ).all()
    )
    office.last_activity_at = max(seen.values(), default=None)
    if team:
        office.team = [
            StaffMember(
                name=u.name,
                email=u.email,
                role=u.role,
                status="invited"
                if u.password_hash is None
                else "unconfirmed"
                if u.email_confirmed_at is None
                else "active",
                last_seen_at=seen.get(u.id),
            )
            for u in sorted(users, key=lambda u: u.name.lower())
        ]
    office.projects = {
        str(status): count
        for status, count in (
            await session.execute(
                select(Project.status, func.count())
                .where(Project.deleted_at.is_(None))  # as the painel counts them
                .group_by(Project.status)
            )
        ).all()
    }
    for status in ProjectStatus:
        office.projects.setdefault(str(status), 0)
    connection = await session.scalar(select(StorageConnection))
    if connection is not None:
        office.storage = str(connection.kind)
        office.writer_status = str(connection.writer_status)
        office.reader_status = str(connection.reader_status)
        office.drive_account = connection.account_email
    office.emails_sent = await session.scalar(
        select(func.count()).where(
            NotificationDelivery.status == DeliveryStatus.SENT,
            NotificationDelivery.updated_at > now - RECENT,
        )
    )
    links, downloads = (
        await session.execute(select(func.count(), func.coalesce(func.sum(ShareLink.downloads), 0)))
    ).one()
    office.share_links, office.downloads = links, downloads

    if team:
        projects = list(await session.scalars(select(Project).where(Project.deleted_at.is_(None))))
        ids = [p.id for p in projects]
        details = list(
            await session.scalars(select(ProjectDetail).where(ProjectDetail.project_id.in_(ids)))
        )
        filled = [
            d
            for d in details
            if (d.value_text and d.value_text.strip())
            or d.value_number is not None
            or d.value_date is not None
        ]
        stages = list(
            await session.scalars(select(ProjectStage).where(ProjectStage.project_id.in_(ids)))
        )
        settings = await session.scalar(select(OfficeProfile))
        office.usage = {
            "projects": len(projects),
            "descriptions": sum(bool(p.description.strip()) for p in projects),
            "covers": sum(p.cover_file_id is not None for p in projects),
            "projects_with_details": len({d.project_id for d in filled}),
            "details": len(filled),
            "stages": len(stages),
            "completed_stages": sum(s.completed_at is not None for s in stages),
            "stage_notes": sum(bool(s.notes.strip()) for s in stages),
            "meetings": await session.scalar(
                select(func.count()).select_from(Meeting).where(Meeting.project_id.in_(ids))
            ),
            "logo": int(settings is not None and settings.logo_file_id is not None),
        }
        for project in projects:
            office.project_types[project.project_type] = (
                office.project_types.get(project.project_type, 0) + 1
            )
        office.link_statuses = {"active": 0, "expired": 0, "disabled": 0}
        for link in await session.scalars(select(ShareLink)):
            state = (
                "disabled"
                if link.disabled_at
                else "expired"
                if link.expires_at and link.expires_at <= now
                else "active"
            )
            office.link_statuses[state] += 1


async def summaries(
    sessionmaker: async_sessionmaker, now: datetime, slug: str | None = None
) -> list[OfficeSummary]:
    """Every office's summary, or only `slug`'s (with its team)."""
    async with sessionmaker() as session:
        tenants = await _tenants(session)
    out = []
    for tenant, hosts in tenants:
        if slug is not None and tenant.slug != slug:
            continue
        office = OfficeSummary(
            id=tenant.id,
            slug=tenant.slug,
            name=tenant.name,
            status=str(tenant.status),
            created_at=tenant.created_at,
            hosts=hosts,
            features=sorted(known_features(tenant.features)),
        )
        async with sessionmaker() as session:
            scope_to_tenant(session.sync_session, tenant.id)
            await _fill(session, office, now, team=slug is not None)
        out.append(office)
    return out
