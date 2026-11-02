"""Client updates by WhatsApp (A44): what the messages say, who gets them, and
sending a batch's message to each number.

The batches are the emails' (digest.py): the same news, gathered and checked
the same way, goes to each subscribed number as one message. Who gets it: a
number subscribed to the project, that hasn't replied SAIR (to any project:
`WhatsAppOptOut`), in an office with the `whatsapp_updates` feature (A40).
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.isolation import scope_to_tenant
from backend.notifications.models import (
    DeliveryStatus,
    NotificationBatch,
    ProjectWhatsApp,
    WhatsAppDelivery,
    WhatsAppMessageSeen,
    WhatsAppOptOut,
    WhatsAppSource,
    WhatsAppStatus,
)
from backend.notifications.office import Office, office_of
from backend.notifications.texts import t
from backend.notifications.whatsapp import (
    INVITE_TEMPLATE,
    LANGUAGES,
    NOT_ON_WHATSAPP,
    UPDATE_TEMPLATE,
    WELCOME_TEMPLATE,
    WhatsAppError,
    WhatsAppMessage,
    WhatsAppSender,
    may_receive,
    opt_out_hash,
    param,
    token,
    whatsapp_sender_for,
)
from backend.projects.models import Project
from backend.settings import Settings
from backend.tenancy.models import Locale

if TYPE_CHECKING:
    from backend.notifications.digest import Summary

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 5  # as an email's: then that number is given up on for this message
STAGES_LISTED = 3  # more changed stages read as "e mais 2 etapas"


def _w(locale: Locale, key: str, count: int | None = None, **values) -> str:
    return t(locale, key, count, section="whatsapp", **values)


# -- what the messages say ------------------------------------------------------------


def _when(locale: Locale, starts: datetime) -> str:
    time = f"{starts.hour}h" if starts.minute == 0 else f"{starts.hour}h{starts.minute:02d}"
    if locale is Locale.EN:
        time = starts.strftime("%H:%M")
    return _w(locale, "when", date=starts.strftime("%d/%m"), time=time)


def news_line(locale: Locale, summary: Summary) -> str:
    """The update's news on one line (a template's part can't break lines): the
    stages in page order, then the project, then the meeting, as the email."""
    parts: list[str] = []
    stages = [s for s in summary.news if s.name]
    # Files in a stage removed meanwhile are on the page under no stage.
    loose = sum(s.files for s in summary.news if not s.name)
    if len(stages) == 1:
        [stage] = stages
        files = _w(locale, "filesNew", count=stage.files) if stage.files else None
        if files and stage.progress:
            key = "inStageCompleted" if stage.progress == "completed" else "inStageReopened"
            parts.append(_w(locale, key, files=files, stage=stage.name))
        elif files:
            parts.append(_w(locale, "inStage", files=files, stage=stage.name))
        elif stage.progress:
            key = "stageCompleted" if stage.progress == "completed" else "stageReopened"
            parts.append(_w(locale, key, stage=stage.name))
    elif stages:
        for stage in stages[:STAGES_LISTED]:
            changes = []
            if stage.files:
                changes.append(_w(locale, "filesNew", count=stage.files))
            if stage.progress:
                key = "markedCompleted" if stage.progress == "completed" else "markedReopened"
                changes.append(_w(locale, key))
            parts.append(_w(locale, "stageList", stage=stage.name, changes=", ".join(changes)))
        if len(stages) > STAGES_LISTED:
            parts.append(_w(locale, "moreStages", count=len(stages) - STAGES_LISTED))
    if loose:
        parts.append(_w(locale, "filesNew", count=loose))
    if summary.project_completed:
        parts.append(_w(locale, "projectCompleted"))
    if summary.meeting is not None:
        kind, title, starts = summary.meeting
        if kind == "cleared" or starts is None:
            parts.append(_w(locale, "meetingCleared", title=title))
        else:
            key = "meetingScheduled" if kind == "scheduled" else "meetingChanged"
            parts.append(_w(locale, key, title=title, when=_when(locale, starts)))
    return _w(locale, "separator").join(parts)


def _with_footer(locale: Locale, text: str) -> str:
    return f"{text}\n\n{_w(locale, 'footer')}"


def update_message(
    office: Office, project: Project, phone: str, news: str, link: str, callback: str
) -> WhatsAppMessage:
    locale = office.locale
    params = (param(project.name), param(office.name), param(news), link)
    text = _w(locale, "update", project=params[0], office=params[1], news=params[2], link=link)
    return WhatsAppMessage(
        to=phone,
        text=_with_footer(locale, text),
        template=UPDATE_TEMPLATE,
        language=LANGUAGES[locale],
        params=params,
        callback=callback,
    )


def greeting(
    settings: Settings, office: Office, tenant_id: uuid.UUID, project: Project, recipient
) -> WhatsAppMessage:
    """The first message to a number: the welcome to a client who signed up, or
    the question to one staff added, whose buttons say which number answers."""
    locale = office.locale
    project_name, office_name = param(project.name), param(office.name)
    callback = token(settings, "sent", tenant_id, recipient.id)
    if recipient.source is WhatsAppSource.STAFF:
        text = _w(locale, "invite", office=office_name, project=project_name)
        yes, no = _w(locale, "inviteYes"), _w(locale, "inviteNo")
        return WhatsAppMessage(
            to=recipient.phone,
            text=f"{text}\n\n[{yes}] [{no}]",
            template=INVITE_TEMPLATE,
            language=LANGUAGES[locale],
            params=(office_name, project_name),
            buttons=(
                token(settings, "yes", tenant_id, recipient.id),
                token(settings, "no", tenant_id, recipient.id),
            ),
            callback=callback,
        )
    text = _w(locale, "welcome", project=project_name, office=office_name)
    return WhatsAppMessage(
        to=recipient.phone,
        text=_with_footer(locale, text),
        template=WELCOME_TEMPLATE,
        language=LANGUAGES[locale],
        params=(project_name, office_name),
        callback=callback,
    )


def reply(locale: Locale, phone: str, key: str, **values) -> WhatsAppMessage:
    """A free-text answer to what the client just wrote (24-hour window)."""
    return WhatsAppMessage(to=phone, text=_w(locale, key, **values))


# -- SAIR -----------------------------------------------------------------------------


async def opted_out(db: AsyncSession, settings: Settings, phones: set[str]) -> set[str]:
    """Those of `phones` that replied SAIR."""
    if not phones:
        return set()
    by_hash = {opt_out_hash(settings, p): p for p in phones}
    found = await db.scalars(
        select(WhatsAppOptOut.phone_hash).where(WhatsAppOptOut.phone_hash.in_(by_hash))
    )
    return {by_hash[h] for h in found}


async def opt_out(db: AsyncSession, settings: Settings, phone: str) -> None:
    await db.execute(
        insert(WhatsAppOptOut)
        .values(phone_hash=opt_out_hash(settings, phone))
        .on_conflict_do_nothing()
    )


async def opt_back_in(
    db: AsyncSession, settings: Settings, phone: str, chosen_at: datetime | None = None
) -> None:
    """The client chose the updates again: their own choice lifts their SAIR, if
    it came after it (`chosen_at`: when they tapped; Meta may deliver it late)."""
    query = delete(WhatsAppOptOut).where(WhatsAppOptOut.phone_hash == opt_out_hash(settings, phone))
    if chosen_at is not None:
        query = query.where(WhatsAppOptOut.created_at < chosen_at)
    await db.execute(query)


async def first_time(db: AsyncSession, message_id: str) -> bool:
    """Whether this webhook message is new: recorded as handled in the caller's
    transaction, so it counts only if what it changed is saved too."""
    if not message_id:
        return True
    found = await db.scalar(
        insert(WhatsAppMessageSeen)
        .values(message_id=message_id)
        .on_conflict_do_nothing()
        .returning(WhatsAppMessageSeen.message_id)
    )
    return found is not None


# -- greeting a new number ------------------------------------------------------------


async def greet(
    db: AsyncSession,
    settings: Settings,
    sender: WhatsAppSender | None,
    office: Office,
    tenant_id: uuid.UUID,
    project: Project,
    recipient: ProjectWhatsApp,
    now: datetime,
) -> bool:
    """Send a number its first message; whether it went. Not sent, it is tried
    again by the maintenance pass (`greeted_at` stays None)."""
    if sender is None or not may_receive(settings, recipient.phone):
        return False
    if await opted_out(db, settings, {recipient.phone}):
        return False
    try:
        await sender.send(greeting(settings, office, tenant_id, project, recipient))
    except WhatsAppError as error:
        if error.code == NOT_ON_WHATSAPP:
            recipient.status = WhatsAppStatus.UNREACHABLE
        log.error(
            "whatsapp: greeting a number of %s/%s failed: %s", tenant_id, project.id, error.detail
        )
        return False
    recipient.greeted_at = now
    return True


async def greet_now(
    sessionmaker, settings: Settings, http, tenant_id: uuid.UUID, recipient_ids: list[uuid.UUID]
) -> None:
    """After a request added numbers: their first messages, in a session of their
    own (the request's has ended). What fails, the maintenance pass sends later."""
    sender = whatsapp_sender_for(settings, http)
    if sender is None or not recipient_ids:
        return
    async with sessionmaker() as db:
        scope_to_tenant(db.sync_session, tenant_id)
        office = await office_of(db, settings, tenant_id)
        for recipient in await db.scalars(
            select(ProjectWhatsApp).where(
                ProjectWhatsApp.id.in_(recipient_ids), ProjectWhatsApp.greeted_at.is_(None)
            )
        ):
            project = await db.scalar(select(Project).where(Project.id == recipient.project_id))
            if project is not None:
                await greet(
                    db, settings, sender, office, tenant_id, project, recipient, datetime.now(UTC)
                )
        await db.commit()


async def ungreeted(db: AsyncSession, project_id: uuid.UUID, before: datetime) -> list:
    """Numbers whose first message hasn't gone yet, added before `before` (so a
    request still sending it isn't raced)."""
    return list(
        await db.scalars(
            select(ProjectWhatsApp).where(
                ProjectWhatsApp.project_id == project_id,
                ProjectWhatsApp.greeted_at.is_(None),
                ProjectWhatsApp.status.in_((WhatsAppStatus.INVITED, WhatsAppStatus.SUBSCRIBED)),
                ProjectWhatsApp.created_at < before,
            )
        )
    )


# -- a batch's messages ---------------------------------------------------------------


async def receivers(
    db: AsyncSession, settings: Settings, office: Office, project: Project
) -> set[str]:
    """Who may get this project's WhatsApp updates now."""
    if not office.whatsapp:
        return set()
    subscribed = {
        r.phone
        for r in await db.scalars(
            select(ProjectWhatsApp).where(
                ProjectWhatsApp.project_id == project.id,
                ProjectWhatsApp.status == WhatsAppStatus.SUBSCRIBED,
            )
        )
        if may_receive(settings, r.phone)
    }
    return subscribed - await opted_out(db, settings, subscribed)


def start(db: AsyncSession, batch: NotificationBatch, phones: set[str]) -> None:
    """The batch is going out: its numbers are fixed from now on."""
    for phone in sorted(phones):
        db.add(WhatsAppDelivery(batch_id=batch.id, phone=phone, status=DeliveryStatus.PENDING))


async def send_batch(
    db: AsyncSession,
    settings: Settings,
    sender: WhatsAppSender | None,
    office: Office,
    project: Project,
    batch: NotificationBatch,
    summary: Summary,
    link: str,
    allowed: set[str],
) -> tuple[int, bool]:
    """Send the batch's message to each number still due it: how many went, and
    whether any is left to try on the next pass."""
    deliveries = list(
        await db.scalars(
            select(WhatsAppDelivery)
            .where(WhatsAppDelivery.batch_id == batch.id)
            .order_by(WhatsAppDelivery.phone)
        )
    )
    due = [
        d
        for d in deliveries
        if d.status is not DeliveryStatus.SENT and d.attempts < MAX_ATTEMPTS and d.phone in allowed
    ]
    if not due:
        return 0, False
    news = news_line(office.locale, summary)
    if sender is None or not news:
        # WhatsApp not set up here (deployed without Meta's settings), or nothing
        # it can say: the email goes on its own, and the batch isn't held for it.
        return 0, False
    recipients = {
        r.phone: r.id
        for r in await db.scalars(
            select(ProjectWhatsApp).where(ProjectWhatsApp.project_id == project.id)
        )
    }
    sent, pending = 0, False
    for delivery in due:
        callback = token(
            settings, "sent", project.tenant_id, recipients.get(delivery.phone, batch.id)
        )
        delivery.attempts += 1
        try:
            delivery.provider_id = await sender.send(
                update_message(office, project, delivery.phone, news, link, callback)
            )
            delivery.status = DeliveryStatus.SENT
            sent += 1
        except WhatsAppError as error:
            delivery.status = DeliveryStatus.FAILED
            log.error(
                "whatsapp: sending batch %s of %s/%s failed (attempt %s): %s",
                batch.id,
                project.tenant_id,
                project.id,
                delivery.attempts,
                error.detail,
            )
            pending = pending or delivery.attempts < MAX_ATTEMPTS
    return sent, pending
