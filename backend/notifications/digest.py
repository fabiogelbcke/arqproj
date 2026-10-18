"""Client email updates (A12, A32, plan section 14): a project's changes gathered
into one email, sent once things have been quiet.

Each maintenance pass, for each published project:

1. Changes not yet in an email (all but notes, A32) join the project's open batch.
2. The batch is due 45 minutes after its last change, or 2 hours after its first.
3. Just before sending: the project must still be published, files must still be
   on its page and unchanged for a minute (section 11's settling check), and the
   address still subscribed; outside production, only the office's own staff.
   Nothing left to say, or nobody to say it to: the batch is dropped.
4. One email per address, each with its own idempotency key and recorded as sent,
   so a retry never sends twice. A failure is retried on the next pass.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta
from html import escape
from pathlib import Path
from string import Template

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.notifications.email import Email, EmailError, EmailSender
from backend.notifications.events import CLIENT_VISIBLE
from backend.notifications.models import (
    BatchState,
    DeliveryStatus,
    EventKind,
    NotificationBatch,
    NotificationDelivery,
    ProjectEvent,
    ProjectRecipient,
    RecipientStatus,
)
from backend.notifications.office import Office
from backend.notifications.texts import t
from backend.projects.enums import ProjectStatus
from backend.projects.models import Meeting, Project, ProjectSlug, ProjectStage
from backend.security import keys
from backend.settings import Settings
from backend.web.page_files import _in_project, stage_groups
from backend.web.page_stages import _title

log = logging.getLogger(__name__)

QUIET = timedelta(minutes=45)  # A12
HOLD = timedelta(hours=2)
SETTLE = timedelta(minutes=1)  # section 11: a file still changing waits
EMAILED = [kind for kind in EventKind if kind is not EventKind.NOTE_CHANGED]  # A32
MEETINGS = {EventKind.MEETING_SCHEDULED, EventKind.MEETING_CHANGED, EventKind.MEETING_CLEARED}
FILES_LISTED = 3  # names shown per stage; the rest are "and N more"
MAX_ATTEMPTS = 5  # then that address is given up on for this email (logged)
UNSUBSCRIBE_PURPOSE = "unsubscribe"
# Inline styles only: email programs ignore stylesheets.
_TEMPLATE = Template((Path(__file__).parent / "templates" / "update.html").read_text("utf-8"))


# -- unsubscribe links ----------------------------------------------------------------


def _hashed(email: str) -> str:
    return hashlib.sha256(email.encode()).hexdigest()[:24]


def unsubscribe_token(settings: Settings, project_id: uuid.UUID, email: str) -> str:
    """The project and the address, never a row: an old email's link keeps working
    even if staff removed the address and added it back (section 14)."""
    plain = json.dumps({"p": str(project_id), "e": email})
    return keys.encrypt(settings.app_secret, UNSUBSCRIBE_PURPOSE, plain)


def unsubscribing(settings: Settings, token: str) -> tuple[uuid.UUID, str] | None:
    try:
        found = json.loads(keys.decrypt(settings.app_secret, UNSUBSCRIBE_PURPOSE, token))
        return uuid.UUID(found["p"]), str(found["e"])
    except (keys.BadToken, ValueError, KeyError, TypeError):
        return None


# -- batches --------------------------------------------------------------------------


async def open_batch(db: AsyncSession, project: Project) -> NotificationBatch | None:
    return await db.scalar(
        select(NotificationBatch).where(
            NotificationBatch.project_id == project.id, NotificationBatch.state == BatchState.OPEN
        )
    )


UNSENT = (BatchState.OPEN, BatchState.SENDING)


async def to_send(db: AsyncSession, project: Project, now: datetime) -> list[NotificationBatch]:
    """Batches going out: any still sending (retried as they are), then the open
    one if it has come due."""
    batches = list(
        await db.scalars(
            select(NotificationBatch)
            .where(NotificationBatch.project_id == project.id, NotificationBatch.state.in_(UNSENT))
            .order_by(NotificationBatch.first_event_at)
        )
    )
    return [b for b in batches if b.state is BatchState.SENDING or is_due(b, now)]


async def drop_unsent(db: AsyncSession, project: Project) -> None:
    for batch in await db.scalars(
        select(NotificationBatch).where(
            NotificationBatch.project_id == project.id, NotificationBatch.state.in_(UNSENT)
        )
    ):
        batch.state, batch.closed_at = BatchState.DROPPED, datetime.now(batch.first_event_at.tzinfo)


async def gather(db: AsyncSession, project: Project) -> NotificationBatch | None:
    """Changes not yet in an email join the project's open batch (made if none)."""
    batch = await open_batch(db, project)
    loose = list(
        await db.scalars(
            select(ProjectEvent)
            .where(
                ProjectEvent.project_id == project.id,
                ProjectEvent.batch_id.is_(None),
                ProjectEvent.kind.in_(EMAILED),
            )
            .order_by(ProjectEvent.occurred_at)
        )
    )
    if loose:
        if batch is None:
            batch = NotificationBatch(
                project_id=project.id,
                first_event_at=loose[0].occurred_at,
                last_event_at=loose[-1].occurred_at,
            )
            db.add(batch)
            await db.flush()
        else:
            batch.last_event_at = max(batch.last_event_at, loose[-1].occurred_at)
        for event in loose:
            event.batch_id = batch.id
    return batch


def is_due(batch: NotificationBatch, now: datetime) -> bool:
    return now - batch.last_event_at >= QUIET or now - batch.first_event_at >= HOLD


# -- who it is from -------------------------------------------------------------------


# -- what it says ---------------------------------------------------------------------


class Wait(Exception):
    """Not now: a file is still changing, or the page's files can't be read."""


async def _visible_files(db: AsyncSession, storage, project: Project) -> dict:
    """Every file the page shows now, by identity, with the stage it is in now."""
    inside = await _in_project(storage, project)
    stages = (
        await db.execute(
            select(ProjectStage.position, ProjectStage.folder_id)
            .where(ProjectStage.project_id == project.id, ProjectStage.folder_id.is_not(None))
            .order_by(ProjectStage.position)
        )
    ).all()
    visible = {}
    for position, folder in stages:
        if folder in inside:
            for _group, _listed, items in await stage_groups(storage, folder):
                for item in items:
                    visible.setdefault(item.identity, (position, item))
    return visible


async def lines_for(
    db: AsyncSession,
    storage,
    project: Project,
    events: list[ProjectEvent],
    office: Office,
    now: datetime,
) -> list[str]:
    """The email's sentences, as things are now (section 14: a file taken down
    meanwhile is left out; several meeting changes read as the latest)."""
    locale = office.locale
    lines: list[str] = []
    files = [e for e in events if e.kind is EventKind.FILE_PUBLISHED]
    if files:
        if storage is None:
            raise Wait  # the page can't show its files now either
        visible = await _visible_files(db, storage, project)
        # As the page shows them now: renamed or moved meanwhile, by their current
        # name and stage; taken down, left out (section 14).
        shown = {e.item_id: visible[e.item_id] for e in files if e.item_id in visible}
        if any(item.modified_at > now - SETTLE for _position, item in shown.values()):
            raise Wait
        titles = {
            s.position: f"{s.position:02d} {await _title(db, s, locale)}"
            for s in await db.scalars(
                select(ProjectStage).where(ProjectStage.project_id == project.id)
            )
        }
        by_stage: dict[int, list[str]] = {}
        for position, item in shown.values():
            name = f"{item.name}.pdf" if item.is_native else item.name  # as the page names it
            by_stage.setdefault(position, []).append(name)
        for position in sorted(by_stage):
            names = by_stage[position]
            listed = ", ".join(names[:FILES_LISTED])
            if len(names) > FILES_LISTED:
                listed += " " + t(locale, "andMore", count=len(names) - FILES_LISTED)
            stage = titles.get(position, f"{position:02d}")
            lines.append(t(locale, "files", count=len(names), stage=stage, names=listed))
    # Progress as it is now: an advance taken back, or a completion reopened,
    # within the quiet period is no news (section 14).
    # The latest advance that still holds: 1 → 2 → 3, then back to 2, is still news
    # of stage 2.
    current = project.current_position or 0
    # Where each stage is now: reordered meanwhile, a stage keeps its identity; a
    # removed one takes its news with it.
    stages = {
        s.id: s
        for s in await db.scalars(select(ProjectStage).where(ProjectStage.project_id == project.id))
    }

    def position_of(event: ProjectEvent) -> int | None:
        if event.stage_id is None:
            return event.stage_position  # recorded before stages were named by identity
        stage = stages.get(event.stage_id)
        return stage.position if stage else None

    holding = [
        (position, e)
        for e in events
        if e.kind is EventKind.STAGE_ADVANCED
        and (position := position_of(e)) is not None
        and position <= current
    ]
    if holding:
        position, last = max(holding, key=lambda pair: pair[0])
        title = await _title(db, stages[last.stage_id], locale) if last.stage_id else last.title
        lines.append(t(locale, "stageAdvanced", stage=f"{position:02d} {title}"))
    if project.status is ProjectStatus.COMPLETED and any(
        e.kind is EventKind.PROJECT_COMPLETED for e in events
    ):
        lines.append(t(locale, "completed"))
    meetings = [e for e in events if e.kind in MEETINGS]
    if meetings:
        upcoming = await db.scalar(
            select(Meeting)
            .where(Meeting.project_id == project.id, Meeting.ends_at > now)
            .order_by(Meeting.starts_at)
            .limit(1)
        )
        if upcoming is not None:
            when = upcoming.starts_at.astimezone(office.zone)
            new = any(e.kind is EventKind.MEETING_SCHEDULED for e in meetings)
            lines.append(
                t(
                    locale,
                    "meetingScheduled" if new else "meetingChanged",
                    title=upcoming.title,
                    when=t(
                        locale, "when", date=when.strftime("%d/%m/%Y"), time=when.strftime("%H:%M")
                    ),
                )
            )
        elif (cleared := [e for e in meetings if e.kind is EventKind.MEETING_CLEARED]) and not any(
            e.kind is EventKind.MEETING_SCHEDULED for e in meetings
        ):
            # Only a meeting the client heard of: one scheduled and cancelled within
            # this quiet period was never news (section 14).
            lines.append(t(locale, "meetingCleared", title=cleared[-1].title))
    return lines


def render(
    office: Office, project: Project, link: str, lines: list[str], unsubscribe: str
) -> tuple[str, str]:
    """The email as HTML (inline styles: email programs ignore stylesheets) and as
    plain text."""
    locale = office.locale
    intro = t(locale, "intro", project=project.name)
    why = t(locale, "why", office=office.name, project=project.name)
    header = (
        f'<img src="{escape(office.logo_url)}" alt="{escape(office.name)}" height="40" '
        'style="height:40px;max-width:200px;display:block">'
        if office.logo_url
        else f'<strong style="font-size:18px">{escape(office.name)}</strong>'
    )
    items = "".join(f'<li style="margin:0 0 8px">{escape(line)}</li>' for line in lines)
    html = _TEMPLATE.substitute(
        lang=locale.value,
        header=header,
        intro=escape(intro),
        items=items,
        link=escape(link),
        open=escape(t(locale, "open")),
        why=escape(why),
        unsubscribe=escape(unsubscribe),
        unsubscribe_label=escape(t(locale, "unsubscribe")),
    )
    text = "\n".join(
        [
            office.name,
            "",
            intro,
            *(f"- {line}" for line in lines),
            "",
            f"{t(locale, 'open')}: {link}",
            "",
            why,
            f"{t(locale, 'unsubscribe')}: {unsubscribe}",
        ]
    )
    return html, text


# -- sending --------------------------------------------------------------------------


async def deliver(
    db: AsyncSession,
    settings: Settings,
    sender: EmailSender,
    storage,
    office: Office,
    project: Project,
    batch: NotificationBatch,
    now: datetime,
) -> int:
    """Send a due batch; how many emails went. A batch with a failure stays
    `sending`, retried by the next pass for the addresses it started with."""
    if project.status not in CLIENT_VISIBLE or project.deleted_at is not None:
        batch.state, batch.closed_at = BatchState.DROPPED, now
        return 0
    events = list(
        await db.scalars(
            select(ProjectEvent)
            .where(ProjectEvent.batch_id == batch.id)
            .order_by(ProjectEvent.occurred_at)
        )
    )
    lines = await lines_for(db, storage, project, events, office, now)  # may raise Wait
    # Who may get it now: subscribed, and outside production staff only (section 14).
    allowed = {
        r.email
        for r in await db.scalars(
            select(ProjectRecipient).where(
                ProjectRecipient.project_id == project.id,
                ProjectRecipient.status == RecipientStatus.SUBSCRIBED,
            )
        )
        if not settings.email_staff_only or r.email in office.staff
    }
    if batch.state is BatchState.OPEN:
        if not lines or not allowed:
            batch.state, batch.closed_at = BatchState.DROPPED, now
            return 0
        # Going out: frozen from now on. Later changes start a new batch, and its
        # addresses are fixed: one added later never gets this old news.
        batch.state = BatchState.SENDING
        for email in sorted(allowed):
            db.add(
                NotificationDelivery(batch_id=batch.id, email=email, status=DeliveryStatus.PENDING)
            )
        await db.flush()
    elif not lines:
        batch.state, batch.closed_at = BatchState.DROPPED, now
        return 0
    slug = await db.scalar(
        select(ProjectSlug.slug).where(ProjectSlug.project_id == project.id, ProjectSlug.is_current)
    )
    link = f"{office.base}/{slug}"
    deliveries = list(
        await db.scalars(
            select(NotificationDelivery)
            .where(NotificationDelivery.batch_id == batch.id)
            .order_by(NotificationDelivery.email)
        )
    )
    sent, pending = 0, False
    for delivery in deliveries:
        if delivery.status is DeliveryStatus.SENT or delivery.attempts >= MAX_ATTEMPTS:
            continue
        if delivery.email not in allowed:
            continue  # unsubscribed (or removed) since it started: not sent
        token = unsubscribe_token(settings, project.id, delivery.email)
        unsubscribe = f"{office.base}/api/emails/unsubscribe/{token}"
        html, text = render(office, project, link, lines, unsubscribe)
        delivery.attempts += 1
        try:
            delivery.provider_id = await sender.send(
                Email(
                    sender=office.sender,
                    to=delivery.email,
                    subject=t(office.locale, "subject", project=project.name),
                    html=html,
                    text=text,
                    reply_to=office.reply_to,
                    # The address hashed: Resend keeps keys in its logs.
                    idempotency_key=f"batch-{batch.id}-{_hashed(delivery.email)}",
                    # Gmail's and Outlook's own "unsubscribe" button (RFC 8058).
                    headers={
                        "List-Unsubscribe": f"<{unsubscribe}>",
                        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
                    },
                )
            )
            delivery.status = DeliveryStatus.SENT
            sent += 1
        except EmailError as error:
            delivery.status = DeliveryStatus.FAILED
            # AGENTS.md: the detail in the log at ERROR, with office and operation.
            log.error(
                "emails: sending batch %s of %s/%s failed (attempt %s): %s",
                batch.id,
                project.tenant_id,
                project.id,
                delivery.attempts,
                error.detail,
            )
            pending = pending or delivery.attempts < MAX_ATTEMPTS
    if not pending:
        batch.state, batch.closed_at = BatchState.SENT, now
    return sent
