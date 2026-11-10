"""Clients sign themselves up for a project's emails (A32, 20 Oct 2026) or
WhatsApp messages (A47).

    POST /api/pages/{slug}/subscribe   from the project page: listed at once, and welcomed
    POST /api/pages/{slug}/whatsapp    the same for a WhatsApp number, if the office has it

No confirmation step (Fabio, 20 Oct 2026): the address is listed straight away and
gets a welcome email saying so, with a small "Não foi você?" link to stop them, the
same unsubscribe link every update carries. Rate-limited per device.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.analytics import capture_visit
from backend.db.engine import get_tenant_session
from backend.identity.emails import is_email, tidy_email
from backend.notifications import whatsapp_updates
from backend.notifications.digest import unsubscribe_token
from backend.notifications.email import Email, EmailError, sender_for
from backend.notifications.models import (
    RECIPIENTS_MAX,
    ProjectRecipient,
    ProjectWhatsApp,
    RecipientStatus,
    WhatsAppSource,
    WhatsAppStatus,
)
from backend.notifications.office import office_of
from backend.notifications.subscribe import welcome_email
from backend.notifications.whatsapp import PHONE_MAX, parse_phone
from backend.projects.enums import ProjectStatus
from backend.projects.models import Project
from backend.tenancy.models import Feature
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


class WhatsAppIn(BaseModel):
    phone: str = Field(max_length=PHONE_MAX)


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
    log.info("emails: an address signed itself up for project %s", project.id)
    if staff is None:
        capture_visit(
            request, tenant.id, "client_email_subscribed", {"returning": recipient is not None}
        )
    stop = unsubscribe_token(request.app.state.settings, project.id, email)
    welcome = welcome_email(
        office,
        project.name,
        f"{office.base}/{slug}?utm_source=email&utm_medium=welcome",
        email,
        f"{office.base}/api/emails/unsubscribe/{stop}",
    )
    background.add_task(_send, request, tenant, welcome)


@router.post(
    "/api/pages/{slug}/whatsapp", status_code=204, responses=documented(403, 404, 409, 422, 429)
)
async def subscribe_whatsapp(
    slug: str,
    body: WhatsAppIn,
    request: Request,
    background: BackgroundTasks,
    staff: CurrentStaff | None = Depends(optional_staff),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> None:
    """Listed at once and sent the welcome, as an email is (A47). Signing up is
    the client's own choice, so it also lifts a SAIR they sent before; staff signed
    in can't make it for them (they add the number in the painel, and the client
    is asked)."""
    if not tenant.has(Feature.WHATSAPP_UPDATES):
        raise ApiError(404, ErrorCode.FEATURE_OFF)
    if staff is not None:
        raise ApiError(403, ErrorCode.WHATSAPP_STAFF)
    project = await _readable(db, slug, staff, request)
    if project.status is ProjectStatus.ARCHIVED:
        raise ApiError(409, ErrorCode.PROJECT_ARCHIVED)
    who = attempts.device(request)
    if not attempts.admit(TRIES, who):
        raise ApiError(429, ErrorCode.TOO_MANY_ATTEMPTS)
    attempts.failed(TRIES, who)
    phone = parse_phone(body.phone)
    if phone is None:
        raise ApiError(422, ErrorCode.INVALID_PHONE)
    settings = request.app.state.settings
    # Locked as staff edits lock it: one change to its numbers at a time.
    project = await db.scalar(select(Project).where(Project.id == project.id).with_for_update())
    if project.status is ProjectStatus.ARCHIVED:
        raise ApiError(409, ErrorCode.PROJECT_ARCHIVED)
    recipient = await db.scalar(
        select(ProjectWhatsApp).where(
            ProjectWhatsApp.project_id == project.id, ProjectWhatsApp.phone == phone
        )
    )
    stopped = bool(await whatsapp_updates.opted_out(db, settings, {phone}))
    if recipient is not None and recipient.status is WhatsAppStatus.SUBSCRIBED and not stopped:
        return  # already in: nothing new to say
    if recipient is None:
        count = await db.scalar(
            select(func.count()).where(ProjectWhatsApp.project_id == project.id)
        )
        if count >= RECIPIENTS_MAX:
            raise ApiError(409, ErrorCode.WHATSAPP_FULL)
        recipient = ProjectWhatsApp(
            project_id=project.id,
            phone=phone,
            status=WhatsAppStatus.SUBSCRIBED,
            source=WhatsAppSource.CLIENT,
        )
        db.add(recipient)
    else:
        recipient.status, recipient.source = WhatsAppStatus.SUBSCRIBED, WhatsAppSource.CLIENT
        recipient.greeted_at = None  # welcomed again
    recipient.answered_at = datetime.now(UTC)  # their latest choice
    await whatsapp_updates.opt_back_in(db, settings, phone, recipient.answered_at)
    await db.flush()
    recipient_id = recipient.id
    await db.commit()
    log.info("whatsapp: a number signed itself up for project %s", project.id)
    if staff is None:
        capture_visit(request, tenant.id, "client_whatsapp_subscribed", {})
    background.add_task(
        whatsapp_updates.greet_now,
        request.app.state.sessionmaker,
        settings,
        getattr(request.app.state, "http", None),
        tenant.id,
        [recipient_id],
    )
