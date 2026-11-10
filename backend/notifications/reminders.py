"""Meeting reminders (A48, plan section 14): by email, and by WhatsApp in offices
with it, to whoever gets the project's updates.

- The day's reminder, at the morning time in the office's time zone; at the
  evening time the day before for a meeting starting less than `EARLY` after the
  morning time, since the pass runs every 10 minutes and a reminder must not
  come at the start or after it.
- For a meeting with a video link, another the set minutes before, whose button
  joins it.

Each goes once per meeting time (`Meeting.reminded_day_for`, `reminded_soon_for`):
moved, a meeting is reminded again. None for a meeting whose time was set after
the reminder came due (the update tells the client), none once it has started,
and due together, only the video one. One attempt: a late reminder is no use, so
a failure is logged, not retried.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from enum import StrEnum
from html import escape

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.notifications import digest, whatsapp_updates
from backend.notifications.email import Email, EmailError, EmailSender
from backend.notifications.models import ProjectWhatsApp, WhatsAppNews
from backend.notifications.notices import Notices
from backend.notifications.office import Office
from backend.notifications.texts import t
from backend.notifications.whatsapp import (
    LANGUAGES,
    REMINDER_TEMPLATE,
    REMINDER_VIDEO_TEMPLATE,
    WhatsAppError,
    WhatsAppMessage,
    WhatsAppSender,
    param,
    short_link,
    token,
)
from backend.projects.enums import AccessMode
from backend.projects.models import Meeting, Project, ProjectSlug
from backend.settings import Settings

log = logging.getLogger(__name__)

# A meeting starting less than this after the morning time is reminded the
# evening before.
EARLY = timedelta(hours=1)
# How far ahead a reminder can be: the evening before, at the earliest.
AHEAD = timedelta(days=2)


class Reminder(StrEnum):
    DAY = "day"  # the morning of, or the evening before
    SOON = "soon"  # before a video meeting


def day_reminder_at(starts: datetime, office: Office, notices: Notices) -> datetime:
    local = starts.astimezone(office.zone)
    morning = datetime.combine(local.date(), notices.morning, office.zone)
    if local - morning < EARLY:
        return datetime.combine(local.date() - timedelta(days=1), notices.evening, office.zone)
    return morning


def due(meeting: Meeting, office: Office, notices: Notices, now: datetime) -> Reminder | None:
    """The reminder to send now, if any."""
    starts = meeting.starts_at
    if starts <= now:
        return None
    if meeting.link:
        at = starts - notices.before
        if now >= at and meeting.reminded_soon_for != starts and meeting.updated_at <= at:
            return Reminder.SOON
    at = day_reminder_at(starts, office, notices)
    if now >= at and meeting.reminded_day_for != starts and meeting.updated_at <= at:
        return Reminder.DAY
    return None


# -- what they say --------------------------------------------------------------------


def _day(office: Office, starts: datetime, now: datetime) -> str:
    """ "hoje às 14:00", "amanhã às 08:00"."""
    local = starts.astimezone(office.zone)
    today: date = now.astimezone(office.zone).date()
    key = "today" if local.date() == today else "tomorrow"
    return t(office.locale, key, section="reminders", time=local.strftime("%H:%M"))


def _r(of: Office, key: str, **values) -> str:
    return t(of.locale, key, section="reminders", **values)


def email_text(
    office: Office, project: Project, meeting: Meeting, kind: Reminder, now: datetime
) -> tuple[str, str]:
    """The email's subject and its opening sentence."""
    time = meeting.starts_at.astimezone(office.zone).strftime("%H:%M")
    when = _day(office, meeting.starts_at, now) if kind is Reminder.DAY else time
    subject = _r(office, "subject", title=meeting.title, when=when)
    key = "emailDay" if kind is Reminder.DAY else "emailSoon"
    return subject, _r(office, key, title=meeting.title, project=project.name, when=when)


def render(
    office: Office,
    project: Project,
    meeting: Meeting,
    kind: Reminder,
    now: datetime,
    link: str,
    unsubscribe: str,
) -> tuple[str, str, str]:
    """Subject, HTML and plain text, in the update emails' frame."""
    subject, lead = email_text(office, project, meeting, kind, now)
    lines = [_r(office, "where", location=meeting.location)] if meeting.location else []
    button = _r(office, "join") if kind is Reminder.SOON else t(office.locale, "open")
    why = t(office.locale, "why", office=office.name, project=project.name)
    html = digest.TEMPLATE.substitute(
        lang=office.locale.value,
        header=digest.email_header(office),
        intro=escape(lead),
        body="".join(f'<p style="margin:0 0 12px">{escape(line)}</p>' for line in lines),
        link=escape(link),
        open=escape(button),
        why=escape(why),
        unsubscribe=escape(unsubscribe),
        unsubscribe_label=escape(t(office.locale, "unsubscribe")),
    )
    text = "\n".join(
        [
            office.name,
            "",
            lead,
            *lines,
            "",
            f"{button}: {link}",
            "",
            why,
            f"{t(office.locale, 'unsubscribe')}: {unsubscribe}",
        ]
    )
    return subject, html, text


def whatsapp_message(
    settings: Settings,
    office: Office,
    project: Project,
    meeting: Meeting,
    kind: Reminder,
    now: datetime,
    phone: str,
    callback: str,
) -> WhatsAppMessage:
    locale = office.locale
    names = (param(meeting.title), param(project.name), param(office.name))
    if kind is Reminder.SOON:
        when = meeting.starts_at.astimezone(office.zone).strftime("%H:%M")
        template, key, label = REMINDER_VIDEO_TEMPLATE, "whatsappSoon", _r(office, "join")
        link = short_link(settings, "join", project.tenant_id, meeting.id)
    else:
        when = _day(office, meeting.starts_at, now)
        template, key = REMINDER_TEMPLATE, "whatsappDay"
        label = t(locale, "openProject", section="whatsapp")
        link = short_link(settings, "page", project.tenant_id, project.id)
    params = (*names, param(when))
    text = _r(office, key, title=params[0], project=params[1], office=params[2], when=params[3])
    footer = t(locale, "footer", section="whatsapp")
    return WhatsAppMessage(
        to=phone,
        text=f"{text}\n\n{footer}",
        template=template,
        language=LANGUAGES[locale],
        params=params,
        links=((label, link),),
        callback=callback,
    )


# -- sending --------------------------------------------------------------------------


async def remind(
    db: AsyncSession,
    settings: Settings,
    sender: EmailSender | None,
    whatsapp: WhatsAppSender | None,
    office: Office,
    project: Project,
    notices: Notices,
    now: datetime,
) -> tuple[int, int]:
    """The project's reminders now due: how many emails and WhatsApp messages
    went. The caller holds the project's lock and commits."""
    meetings = list(
        await db.scalars(
            select(Meeting).where(
                Meeting.project_id == project.id,
                Meeting.starts_at > now,
                Meeting.starts_at <= now + AHEAD,
            )
        )
    )
    reminders = [(m, kind) for m in meetings if (kind := due(m, office, notices, now))]
    if not reminders:
        return 0, 0
    emails = await digest.subscribed(db, settings, office, project) if sender else set()
    phones = (
        await whatsapp_updates.receivers(db, settings, office, project)
        if whatsapp is not None and WhatsAppNews.REMINDERS in notices.whatsapp
        else set()
    )
    rows = {
        r.phone: r.id
        for r in await db.scalars(
            select(ProjectWhatsApp).where(ProjectWhatsApp.project_id == project.id)
        )
    }
    slug = await db.scalar(
        select(ProjectSlug.slug).where(ProjectSlug.project_id == project.id, ProjectSlug.is_current)
    )
    page = f"{office.base}/{slug}"
    emailed = messaged = 0
    for meeting, kind in reminders:
        # Sent for this time, whatever happens below: one attempt (module doc).
        meeting.reminded_day_for = meeting.starts_at
        if kind is Reminder.SOON:
            meeting.reminded_soon_for = meeting.starts_at
        # Behind a password, the page asks for it and shows the link (section 6).
        join = meeting.link and project.access_mode is not AccessMode.PASSWORD
        link = (
            meeting.link
            if kind is Reminder.SOON and join
            else f"{page}?utm_source=email&utm_medium=reminder"
        )
        stamp = int(meeting.starts_at.timestamp())
        for email in sorted(emails):
            unsubscribe = (
                f"{office.base}/api/emails/unsubscribe/"
                f"{digest.unsubscribe_token(settings, project.id, email)}"
            )
            subject, html, text = render(office, project, meeting, kind, now, link, unsubscribe)
            try:
                await sender.send(
                    Email(
                        sender=office.sender,
                        to=email,
                        subject=subject,
                        html=html,
                        text=text,
                        reply_to=office.reply_to,
                        # A pass that fails midway and runs again doesn't send it twice.
                        idempotency_key=f"reminder-{meeting.id}-{kind}-{stamp}-"
                        f"{digest._hashed(email)}",
                        headers={
                            "List-Unsubscribe": f"<{unsubscribe}>",
                            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
                        },
                    )
                )
                emailed += 1
            except EmailError as error:
                log.error(
                    "reminders: emailing %s of %s/%s failed: %s",
                    kind,
                    project.tenant_id,
                    meeting.id,
                    error.detail,
                )
        for phone in sorted(phones):
            # Its status names the number's row, as an update's (webhook: no WhatsApp).
            callback = token(settings, "sent", project.tenant_id, rows[phone])
            message = whatsapp_message(
                settings, office, project, meeting, kind, now, phone, callback
            )
            try:
                await whatsapp.send(message)
                messaged += 1
            except WhatsAppError as error:
                log.error(
                    "reminders: WhatsApp %s of %s/%s failed: %s",
                    kind,
                    project.tenant_id,
                    meeting.id,
                    error.detail,
                )
    return emailed, messaged
