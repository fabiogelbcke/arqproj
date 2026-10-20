"""Clients add themselves to a project's emails (A32, 20 Oct 2026).

    POST /api/pages/{slug}/subscribe      from the project page: emails a link to confirm
    GET  /api/emails/subscribe/{token}    the email's link: asks to confirm
    POST /api/emails/subscribe/{token}    confirmed: the address is listed, subscribed

Only a confirmed address is listed, so nobody can sign a stranger up. Opening the
link only asks (mail scanners open links). The request answers the same whether or
not the address was listed already, and is rate-limited per device.
"""

from __future__ import annotations

import logging
from html import escape

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.engine import get_tenant_session
from backend.identity.emails import is_email, tidy_email
from backend.notifications.email import Email, EmailError, sender_for
from backend.notifications.models import RECIPIENTS_MAX, ProjectRecipient, RecipientStatus
from backend.notifications.office import office_of
from backend.notifications.subscribe import confirm_email, subscribe_token, subscribing
from backend.notifications.texts import t
from backend.projects.enums import ProjectStatus
from backend.projects.models import Project
from backend.tenancy.resolve import CurrentTenant, current_tenant
from backend.web import attempts
from backend.web.auth import CurrentStaff, optional_staff
from backend.web.errors import ApiError, ErrorCode, documented
from backend.web.pages import _readable
from backend.web.unsubscribe import _page

TRIES = "subscribe"  # a few requests per device in 15 minutes

log = logging.getLogger(__name__)
router = APIRouter()


class SubscribeIn(BaseModel):
    email: str = Field(max_length=500)


async def _send(request: Request, tenant: CurrentTenant, email: Email) -> None:
    try:
        http = getattr(request.app.state, "http", None)
        await sender_for(request.app.state.settings, http).send(email)
    except EmailError as error:
        log.error(
            "subscribe email failed: route=/api/pages/{slug}/subscribe tenant=%s %s",
            tenant.slug,
            error.detail,
        )


@router.post(
    "/api/pages/{slug}/subscribe", status_code=202, responses=documented(403, 404, 409, 422, 429)
)
async def subscribe(
    slug: str,
    body: SubscribeIn,
    request: Request,
    background: BackgroundTasks,
    staff: CurrentStaff | None = Depends(optional_staff),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> None:
    project = await _readable(db, slug, staff, request)  # a locked page asks for its password
    if project.status is ProjectStatus.ARCHIVED:
        raise ApiError(409, ErrorCode.PROJECT_ARCHIVED)
    who = attempts.device(request)
    if not attempts.admit(TRIES, who):
        raise ApiError(429, ErrorCode.TOO_MANY_ATTEMPTS)
    attempts.failed(TRIES, who)  # every request counts toward the limit
    email = tidy_email(body.email)
    if not is_email(email):
        raise ApiError(422, ErrorCode.INVALID_EMAIL)
    listed = await db.scalar(
        select(ProjectRecipient.status).where(
            ProjectRecipient.project_id == project.id, ProjectRecipient.email == email
        )
    )
    if listed is RecipientStatus.SUBSCRIBED:
        return  # already gets them: the same answer, no email
    office = await office_of(db, request.app.state.settings, tenant.id)
    token = subscribe_token(request.app.state.settings, project.id, email)
    background.add_task(_send, request, tenant, confirm_email(office, project.name, email, token))


async def _target(request: Request, token: str, db: AsyncSession):
    found = subscribing(request.app.state.settings, token)
    if found is None:
        return None
    project_id, email = found
    project = await db.scalar(select(Project).where(Project.id == project_id))
    if project is None or project.deleted_at is not None:  # another office's, or gone
        return None
    return project, email


def _invalid(tenant: CurrentTenant) -> HTMLResponse:
    text = t(tenant.locale, "subscribeInvalid")
    return _page(tenant, text, f"<p>{escape(text)}</p>", 404)


@router.get("/api/emails/subscribe/{token}", include_in_schema=False)
async def ask(
    request: Request,
    token: str,
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> HTMLResponse:
    found = await _target(request, token, db)
    if found is None:
        return _invalid(tenant)
    project, email = found
    title = t(tenant.locale, "subscribeConfirmTitle", project=project.name)
    ask_text = t(tenant.locale, "subscribeConfirmAsk", email=email, project=project.name)
    button = escape(t(tenant.locale, "subscribeConfirm"))
    return _page(
        tenant,
        title,
        f"<h1 style='font-size:1.25rem'>{escape(title)}</h1><p>{escape(ask_text)}</p>"
        f'<form method="post"><button type="submit" style="font: inherit; padding: 10px 18px">'
        f"{button}</button></form>",
    )


@router.post("/api/emails/subscribe/{token}", include_in_schema=False)
async def confirm(
    request: Request,
    token: str,
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> HTMLResponse:
    found = await _target(request, token, db)
    if found is None:
        return _invalid(tenant)
    project, email = found
    title = t(tenant.locale, "subscribeConfirmTitle", project=project.name)
    recipient = await db.scalar(
        select(ProjectRecipient).where(
            ProjectRecipient.project_id == project.id, ProjectRecipient.email == email
        )
    )
    if recipient is None:
        count = await db.scalar(
            select(func.count()).where(ProjectRecipient.project_id == project.id)
        )
        if count >= RECIPIENTS_MAX:
            full = t(tenant.locale, "subscribeFull")
            return _page(tenant, title, f"<p>{escape(full)}</p>", 409)
        db.add(ProjectRecipient(project_id=project.id, email=email))
    else:
        # Their own choice, even after unsubscribing (staff can't do this for them).
        recipient.status = RecipientStatus.SUBSCRIBED
    await db.commit()
    log.info("emails: an address subscribed itself to project %s", project.id)
    done = t(tenant.locale, "subscribed", email=email, project=project.name)
    return _page(tenant, title, f"<p>{escape(done)}</p>")
