"""Clients sign themselves up for a project's emails (A32, 20 Oct 2026).

    POST /api/pages/{slug}/subscribe   from the project page: listed at once, and welcomed

No confirmation step (Fabio, 20 Oct 2026): the address is listed straight away and
gets a welcome email saying so, with a small "Não foi você?" link to stop them, the
same unsubscribe link every update carries. Rate-limited per device.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.engine import get_tenant_session
from backend.identity.emails import is_email, tidy_email
from backend.notifications.digest import unsubscribe_token
from backend.notifications.email import Email, EmailError, sender_for
from backend.notifications.models import RECIPIENTS_MAX, ProjectRecipient, RecipientStatus
from backend.notifications.office import office_of
from backend.notifications.subscribe import welcome_email
from backend.projects.enums import ProjectStatus
from backend.projects.models import Project
from backend.tenancy.resolve import CurrentTenant, current_tenant
from backend.web import attempts
from backend.web.auth import CurrentStaff, optional_staff
from backend.web.errors import ApiError, ErrorCode, documented
from backend.web.pages import _readable

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
            "welcome email failed: route=/api/pages/{slug}/subscribe tenant=%s %s",
            tenant.slug,
            error.detail,
        )


@router.post(
    "/api/pages/{slug}/subscribe", status_code=204, responses=documented(403, 404, 409, 422, 429)
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
    # The project's row, locked as staff edits lock it: one change to its addresses
    # at a time across both (room for 20, a double click), and its status as of now.
    project = await db.scalar(select(Project).where(Project.id == project.id).with_for_update())
    if project.status is ProjectStatus.ARCHIVED:
        raise ApiError(409, ErrorCode.PROJECT_ARCHIVED)
    recipient = await db.scalar(
        select(ProjectRecipient).where(
            ProjectRecipient.project_id == project.id, ProjectRecipient.email == email
        )
    )
    if recipient is not None and recipient.status is RecipientStatus.SUBSCRIBED:
        return  # already in: nothing new to say
    if recipient is None:
        count = await db.scalar(
            select(func.count()).where(ProjectRecipient.project_id == project.id)
        )
        if count >= RECIPIENTS_MAX:
            raise ApiError(409, ErrorCode.RECIPIENTS_FULL)
        db.add(ProjectRecipient(project_id=project.id, email=email))
    else:
        # Back after unsubscribing: their own choice (staff can't make it for them).
        recipient.status = RecipientStatus.SUBSCRIBED
    office = await office_of(db, request.app.state.settings, tenant.id)
    await db.commit()
    posthog = getattr(request.app.state, "posthog", None)
    if posthog is not None:
        posthog.capture("project_email_subscribed")
    log.info("emails: an address signed itself up for project %s", project.id)
    stop = unsubscribe_token(request.app.state.settings, project.id, email)
    welcome = welcome_email(
        office,
        project.name,
        f"{office.base}/{slug}",
        email,
        f"{office.base}/api/emails/unsubscribe/{stop}",
    )
    background.add_task(_send, request, tenant, welcome)
