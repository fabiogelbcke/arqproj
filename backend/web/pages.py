"""The client's project page (slice 2, A20 revised: React, served from here).

    GET /{slug}                         the page's shell: preview tags, status
    GET /api/pages/{slug}               what the page shows (public, read-only)
    GET /api/pages/{slug}/cover         its cover photo
    GET /api/pages/{slug}/meeting.ics   the next meeting, for a calendar app

A page exists only for a published project (active, completed or archived) that
isn't deleted: a draft, a deleted project and an unknown address all answer the
same "not found", so nobody can tell them apart. The office's signed-in staff
also see drafts and protected pages, with a staff bar (2.6) to publish them.
An address the project had before redirects to the current one (A29). A
password-protected project asks for its password once per device (2.4) and
shows nothing until then; its name stays out of link previews.

The server answers before any script runs: the tags messaging apps read for a
link preview (they don't run scripts), the status, and the redirect. Pages are
private links, so they ask search engines not to index them.
"""

from __future__ import annotations

import html
import logging
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse, RedirectResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.engine import get_tenant_session
from backend.identity.passwords import verify_password
from backend.office.profile import profile as load_profile
from backend.projects.enums import RESERVED_SLUGS, AccessMode, DetailType, ProjectStatus
from backend.projects.models import (
    DetailTypeDef,
    Meeting,
    Project,
    ProjectDetail,
    ProjectSlug,
    ProjectStage,
    ProjectTypeDef,
    ProjectTypeStage,
    StageDef,
)
from backend.security import keys
from backend.tenancy.models import Locale
from backend.tenancy.resolve import CurrentTenant, current_tenant
from backend.web import attempts
from backend.web.auth import CurrentStaff, optional_staff
from backend.web.errors import ApiError, ErrorCode, documented
from backend.web.painel import CONTENT_SECURITY_POLICY, SHELL_CACHE
from backend.web.project_settings import serve_cover

log = logging.getLogger(__name__)
router = APIRouter()

# Published: live or completed, or archived after being published. A draft that
# was archived without ever being published stays unpublished.
PUBLISHED = Project.status.in_((ProjectStatus.ACTIVE, ProjectStatus.COMPLETED)) | (
    (Project.status == ProjectStatus.ARCHIVED) & (Project.archived_from != ProjectStatus.DRAFT)
)
BANNER_SIZE = 2000  # pixels on the long side: the page's full-width cover
PREVIEW_SIZE = 1200  # link previews: WhatsApp skips large images
PAGE_HEADERS = {"X-Robots-Tag": "noindex"}
# Anything only staff or an unlocked device may see must never enter a shared
# cache (plan section 6).
PRIVATE = {"Cache-Control": "private, no-store"}
COVER_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; sandbox",
    "X-Content-Type-Options": "nosniff",
    # Browsers only: a shared cache could keep serving it after the page is
    # given a password (plan section 6).
    "Cache-Control": "private, max-age=300",
    **PAGE_HEADERS,
}


def _text(texts: dict[str, str], locale: Locale) -> str:
    return texts.get(locale.value) or texts[Locale.PT_BR.value]


async def _find(
    db: AsyncSession, slug: str, staff: CurrentStaff | None = None
) -> tuple[Project | None, str | None]:
    """The project at this address that this visitor may see (published, or
    any for the office's staff), and its current address (which differs when
    `slug` is one it had before)."""
    shown = Project.deleted_at.is_(None)
    if staff is None:
        shown &= PUBLISHED
    found = await db.execute(
        select(Project, ProjectSlug.is_current)
        .join(ProjectSlug, ProjectSlug.project_id == Project.id)
        .where(ProjectSlug.slug == slug, shown)
    )
    row = found.first()
    if row is None:
        return None, None
    project, is_current = row
    if is_current:
        return project, slug
    current = await db.scalar(
        select(ProjectSlug.slug).where(ProjectSlug.project_id == project.id, ProjectSlug.is_current)
    )
    return project, current


# -- what the page shows -------------------------------------------------------------


class OfficeOut(BaseModel):
    name: str
    logo_url: str | None


class DetailOut(BaseModel):
    label: str
    type: DetailType
    # Text as typed, an area in m² as a number, or an ISO date; formatted by the page.
    value: str | float


class StageOut(BaseModel):
    title: str
    about: str | None  # what happens in this stage, in the project type's words
    notes: str


class MeetingOut(BaseModel):
    title: str
    starts_at: datetime
    ends_at: datetime
    location: str | None
    link: str | None


class StaffView(BaseModel):
    """Only for the office's signed-in staff: what the staff bar needs."""

    project_id: uuid.UUID
    status: ProjectStatus


class PageOut(BaseModel):
    office: OfficeOut
    locale: Locale
    timezone: str
    name: str
    client_name: str
    project_type: str
    description: str
    cover_url: str | None
    completed: bool
    # Position of the current stage (1-based); None before the first starts.
    current_position: int | None
    last_update: datetime
    details: list[DetailOut]
    stages: list[StageOut]
    next_meeting: MeetingOut | None
    staff: StaffView | None = None


async def _office(db: AsyncSession, tenant: CurrentTenant) -> OfficeOut:
    found = await load_profile(db)
    has_logo = found is not None and found.logo_file_id is not None
    return OfficeOut(
        name=found.display_name if found else tenant.name,
        logo_url=f"/api/office/logo?v={found.updated_at.timestamp():.6f}" if has_logo else None,
    )


def _value(row: ProjectDetail) -> str | float | None:
    if row.value_type is DetailType.AREA and isinstance(row.value_number, Decimal):
        return float(row.value_number)
    if row.value_type is DetailType.DATE and isinstance(row.value_date, date):
        return row.value_date.isoformat()
    return row.value_text


async def _page(db: AsyncSession, tenant: CurrentTenant, project: Project, slug: str) -> PageOut:
    locale = tenant.locale
    type_label = await db.scalar(
        select(ProjectTypeDef.labels).where(ProjectTypeDef.key == project.project_type)
    )
    details = [
        DetailOut(label=_text(labels, locale), type=row.value_type, value=value)
        for row, labels in await db.execute(
            select(ProjectDetail, DetailTypeDef.labels)
            .join(DetailTypeDef, DetailTypeDef.key == ProjectDetail.key)
            .where(ProjectDetail.project_id == project.id)
            .order_by(ProjectDetail.position)
        )
        if (value := _value(row)) is not None
    ]
    stages = []
    for stage, titles, general, own in await db.execute(
        select(ProjectStage, StageDef.titles, StageDef.about, ProjectTypeStage.about)
        .outerjoin(StageDef, StageDef.key == ProjectStage.builtin_key)
        .outerjoin(
            ProjectTypeStage,
            (ProjectTypeStage.stage_key == ProjectStage.builtin_key)
            & (ProjectTypeStage.project_type == project.project_type),
        )
        .where(ProjectStage.project_id == project.id)
        .order_by(ProjectStage.position)
    ):
        if stage.builtin_key is None:  # written by the office, shown as typed
            stages.append(StageOut(title=stage.title, about=stage.about, notes=stage.notes))
        else:
            about = own or general  # the type's own words, else the general text
            stages.append(
                StageOut(title=_text(titles, locale), about=_text(about, locale), notes=stage.notes)
            )
    meeting = await db.scalar(
        select(Meeting)
        .where(Meeting.project_id == project.id, Meeting.ends_at > datetime.now(UTC))
        .order_by(Meeting.starts_at)
        .limit(1)
    )
    return PageOut(
        office=await _office(db, tenant),
        locale=locale,
        timezone=tenant.timezone,
        name=project.name,
        client_name=project.client_name,
        project_type=_text(type_label, locale),
        description=project.description,
        cover_url=(
            f"/api/pages/{slug}/cover?v={project.updated_at.timestamp():.6f}"
            if project.cover_file_id
            else None
        ),
        completed=project.status is ProjectStatus.COMPLETED,
        current_position=project.current_position,
        last_update=project.last_activity_at or project.created_at,
        details=details,
        stages=stages,
        next_meeting=(
            MeetingOut(
                title=meeting.title,
                starts_at=meeting.starts_at,
                ends_at=meeting.ends_at,
                location=meeting.location,
                link=meeting.link,
            )
            if meeting
            else None
        ),
    )


UNLOCK_PURPOSE = "page-unlock"
UNLOCK_DAYS = 90  # a device stays unlocked this long (Fabio, 16 Oct 2026)


def _unlock_cookie(project: Project) -> str:
    return f"unlock-{project.id.hex[:16]}"


def _unlocked(request: Request, project: Project) -> bool:
    """This device typed the project's current password (A06): changing the
    password or the access mode bumps `access_version`, ending older unlocks."""
    token = request.cookies.get(_unlock_cookie(project))
    if not token:
        return False
    try:
        found = keys.verify(request.app.state.settings.app_secret, UNLOCK_PURPOSE, token)
    except keys.BadToken:
        return False
    return found.get("p") == str(project.id) and found.get("v") == project.access_version


async def _readable(
    db: AsyncSession, slug: str, staff: CurrentStaff | None, request: Request
) -> Project:
    """The project behind a current address, if this visitor may see its page."""
    project, current = await _find(db, slug, staff)
    if project is None or current != slug:
        raise ApiError(404, ErrorCode.PAGE_NOT_FOUND)
    locked = project.access_mode is AccessMode.PASSWORD and not _unlocked(request, project)
    if locked and staff is None:
        raise ApiError(403, ErrorCode.PAGE_LOCKED)  # the password step comes in 2.4
    return project


@router.get("/api/pages/{slug}", responses=documented(403, 404))
async def page(
    request: Request,
    slug: str,
    response: Response,
    staff: CurrentStaff | None = Depends(optional_staff),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> PageOut:
    project = await _readable(db, slug, staff, request)
    shown = await _page(db, tenant, project, slug)
    if staff is not None:
        shown.staff = StaffView(project_id=project.id, status=project.status)
    if staff is not None or project.access_mode is AccessMode.PASSWORD:
        response.headers.update(PRIVATE)
    return shown


@router.get("/api/pages/{slug}/cover", include_in_schema=False)
async def page_cover(
    request: Request,
    slug: str,
    preview: bool = False,
    staff: CurrentStaff | None = Depends(optional_staff),
    db: AsyncSession = Depends(get_tenant_session),
) -> Response:
    try:
        project = await _readable(db, slug, staff, request)
    except ApiError:
        return Response(status_code=404, headers=PAGE_HEADERS)
    size = PREVIEW_SIZE if preview else BANNER_SIZE
    private = staff is not None or project.access_mode is AccessMode.PASSWORD
    headers = {**COVER_HEADERS, **PRIVATE} if private else COVER_HEADERS
    return await serve_cover(request, db, project, size, headers)


class UnlockIn(BaseModel):
    password: str = Field(max_length=200)


@router.post("/api/pages/{slug}/unlock", status_code=204, responses=documented(401, 404, 429))
async def unlock(
    request: Request,
    slug: str,
    body: UnlockIn,
    db: AsyncSession = Depends(get_tenant_session),
) -> Response:
    """The client types the project's password once per device (A06)."""
    project, current = await _find(db, slug)
    if project is None or current != slug or project.access_mode is not AccessMode.PASSWORD:
        raise ApiError(404, ErrorCode.PAGE_NOT_FOUND)
    who, key = attempts.device(request), str(project.id)
    if not attempts.admit(key, who):  # reserved before the (slow) hash check
        raise ApiError(429, ErrorCode.TOO_MANY_ATTEMPTS)
    try:
        right = await verify_password(project.password_hash, body.password)
    except BaseException:
        attempts.failed(key, who)  # a try that didn't finish still counts
        raise
    if not right:
        attempts.failed(key, who)
        log.info("wrong page password for %s", slug)
        raise ApiError(401, ErrorCode.WRONG_PAGE_PASSWORD)
    attempts.succeeded(key, who)
    token = keys.sign(
        request.app.state.settings.app_secret,
        UNLOCK_PURPOSE,
        {"p": str(project.id), "v": project.access_version},
        UNLOCK_DAYS * 86400,
    )
    response = Response(status_code=204, headers=PAGE_HEADERS)
    response.set_cookie(
        _unlock_cookie(project),
        token,
        max_age=UNLOCK_DAYS * 86400,
        path="/",
        httponly=True,
        samesite="lax",
        secure=request.app.state.settings.deployed,
    )
    return response


def _origin(request: Request, tenant: CurrentTenant) -> str:
    """The office's address as clients use it: always https when deployed (Cloud
    Run's front end speaks https; the app itself sees plain http)."""
    if request.app.state.settings.deployed:
        return f"https://{tenant.primary_host}"
    return f"{request.url.scheme}://{request.headers.get('host', tenant.primary_host)}"


def _ics_time(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _ics_text(value: str) -> str:
    """RFC 5545 text: backslash, semicolon, comma and line breaks escaped."""
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
    )


@router.get("/api/pages/{slug}/meeting.ics", include_in_schema=False)
async def meeting_ics(
    request: Request,
    slug: str,
    staff: CurrentStaff | None = Depends(optional_staff),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> Response:
    """For Apple Calendar, Outlook and others ("Adicionar à agenda")."""
    try:
        project = await _readable(db, slug, staff, request)
    except ApiError:
        return Response(status_code=404, headers=PAGE_HEADERS)
    meeting = await db.scalar(
        select(Meeting)
        .where(Meeting.project_id == project.id, Meeting.ends_at > datetime.now(UTC))
        .order_by(Meeting.starts_at)
        .limit(1)
    )
    if meeting is None:
        return Response(status_code=404, headers=PAGE_HEADERS)
    office = (await _office(db, tenant)).name
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Portal de projetos//PT",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{meeting.id}@{tenant.primary_host}",
        f"DTSTAMP:{_ics_time(datetime.now(UTC))}",
        f"DTSTART:{_ics_time(meeting.starts_at)}",
        f"DTEND:{_ics_time(meeting.ends_at)}",
        f"SUMMARY:{_ics_text(f'{meeting.title} · {project.name}')}",
        f"DESCRIPTION:{_ics_text(f'{office}: {_origin(request, tenant)}/{slug}')}",
    ]
    if meeting.location:
        lines.append(f"LOCATION:{_ics_text(meeting.location)}")
    if meeting.link:
        lines.append(f"URL:{meeting.link}")
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return Response(
        "\r\n".join(lines) + "\r\n",
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="reuniao.ics"',
            **PAGE_HEADERS,
            # Staff-only or behind a password: never in a shared cache.
            **(PRIVATE if staff is not None or project.access_mode is AccessMode.PASSWORD else {}),
        },
    )


# -- the page's shell ----------------------------------------------------------------


def _summary(description: str, limit: int = 200) -> str:
    """The description's first paragraph, for a link preview."""
    first = next((line.strip() for line in description.splitlines() if line.strip()), "")
    first = first.removeprefix("- ")
    return first if len(first) <= limit else first[: limit - 1].rstrip() + "…"


def _head(tags: dict[str, str], title: str) -> str:
    out = [f"<title>{html.escape(title)}</title>"]
    for name, content in tags.items():
        attribute = "property" if name.startswith("og:") else "name"
        out.append(f'<meta {attribute}="{name}" content="{html.escape(content, quote=True)}" />')
    return "\n    ".join(out)


@router.get("/{slug}", include_in_schema=False)
async def shell(
    request: Request,
    slug: str,
    staff: CurrentStaff | None = Depends(optional_staff),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> Response:
    if slug in RESERVED_SLUGS:
        return PlainTextResponse("Not found", status_code=404)
    shell_file = Path(request.app.state.settings.frontend_dist) / "client.html"
    if not shell_file.is_file():
        return PlainTextResponse(
            "The client page is not built. Run `make build` (or `make dev`).", status_code=503
        )
    project, current = await _find(db, slug, staff)
    if project is not None and current != slug:
        query = f"?{request.url.query}" if request.url.query else ""
        # Permanent, but not cached forever: a slug may later point back here.
        return RedirectResponse(
            f"/{current}{query}",
            status_code=301,
            headers={"Cache-Control": "no-cache", **PAGE_HEADERS},
        )

    office = (await _office(db, tenant)).name
    tags = {"robots": "noindex"}
    if project is None:
        status, title = 404, office
    elif project.access_mode is AccessMode.PASSWORD:
        # The name of a protected project stays private, even in link previews.
        status, title = 200, office
        tags |= {"og:title": office, "og:type": "website"}
    else:
        status, title = 200, f"{project.name} · {office}"
        tags |= {"og:title": project.name, "og:site_name": office, "og:type": "website"}
        if summary := _summary(project.description):
            tags |= {"description": summary, "og:description": summary}
        if project.cover_file_id:
            version = f"{project.updated_at.timestamp():.6f}"
            tags["og:image"] = (
                f"{_origin(request, tenant)}/api/pages/{slug}/cover?v={version}&preview=true"
            )
    document = shell_file.read_text("utf-8").replace("<!--page-head-->", _head(tags, title))
    return Response(
        document,
        status_code=status,
        media_type="text/html; charset=utf-8",
        headers={
            "Cache-Control": SHELL_CACHE,
            "Content-Security-Policy": CONTENT_SECURITY_POLICY,
            **PAGE_HEADERS,
            **(PRIVATE if staff is not None else {}),
        },
    )
