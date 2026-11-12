"""WhatsApp's link buttons (A47).

    GET /w/{code}   on to a project's page, or its next meeting for a calendar

A template's link button is fixed at Meta up to its last part, and each office
has its own address, so the buttons point here, on Unio's own address, with a
signed code naming the office and the project (`short_link`):

- "page": a redirect to the project's page;
- "agenda": the project's next meeting as a calendar file, as the page's
  "Adicionar à agenda" gives it; the page instead when none is to come (it was
  cancelled or has passed since the message), or when the page has a password.

The code is the client's message: it was sent only to their number. One that
doesn't check out, an office no longer active, or a project that is gone or no
longer shown to clients answers "not found", as an unknown page does.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select

from backend.db.isolation import scope_to_tenant
from backend.notifications.events import CLIENT_VISIBLE
from backend.notifications.office import office_of
from backend.notifications.whatsapp import LINK_PATH, read_token
from backend.projects.enums import AccessMode
from backend.projects.models import Meeting, Project, ProjectSlug
from backend.tenancy.models import Tenant, TenantStatus
from backend.web.pages import (
    CALENDAR_HEADERS,
    CALENDAR_TYPE,
    PAGE_HEADERS,
    PRIVATE,
    calendar_file,
)

router = APIRouter(include_in_schema=False)


@router.get(LINK_PATH + "{code}")
async def follow(request: Request, code: str) -> Response:
    settings = request.app.state.settings
    found = read_token(settings, code)
    if found is None or found.action not in ("page", "agenda"):
        return Response(status_code=404, headers=PAGE_HEADERS)
    async with request.app.state.sessionmaker() as db:
        scope_to_tenant(db.sync_session, found.tenant_id)
        tenant = await db.get(Tenant, found.tenant_id)
        project = await db.scalar(
            select(Project).where(Project.id == found.recipient_id, Project.deleted_at.is_(None))
        )
        if (
            tenant is None
            or tenant.status is not TenantStatus.ACTIVE
            or project is None
            or project.status not in CLIENT_VISIBLE
        ):
            return Response(status_code=404, headers=PAGE_HEADERS)
        slug = await db.scalar(
            select(ProjectSlug.slug).where(
                ProjectSlug.project_id == project.id, ProjectSlug.is_current
            )
        )
        office = await office_of(db, settings, tenant.id)
        page = f"{office.base}/{slug}"
        # Behind a password, the page asks for it first and offers the calendar
        # itself: the link isn't a way round the password (plan section 6).
        if found.action == "agenda" and project.access_mode is not AccessMode.PASSWORD:
            meeting = await db.scalar(
                select(Meeting)
                .where(Meeting.project_id == project.id, Meeting.ends_at > datetime.now(UTC))
                .order_by(Meeting.starts_at)
                .limit(1)
            )
            if meeting is not None:
                host = office.base.split("://", 1)[1].split(":", 1)[0]
                return Response(
                    calendar_file(meeting, project.name, office.name, page, host),
                    media_type=CALENDAR_TYPE,
                    headers={**CALENDAR_HEADERS, **PAGE_HEADERS, **PRIVATE},
                )
    # Tagged so page analytics (A39) can tell visits that came from WhatsApp.
    return RedirectResponse(f"{page}?utm_source=whatsapp&utm_medium=update", status_code=302)
