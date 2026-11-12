"""Clients' comments emailed to the office's staff (A49), from the maintenance pass.

A project's new client comments go in one email, once quiet for a few minutes
(or a while after the first, if they keep coming), to the project's members
(A41) or, with none, to every staff account. The comments an email holds are
fixed when it first goes (`alert_batch`): a retry after a failure sends that same
email under the same idempotency key per address, so nobody gets it twice, and
comments arriving meanwhile wait for the next. They are marked as told once
every address got it.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timedelta
from html import escape
from pathlib import Path
from string import Template

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.comments.models import Author, Comment
from backend.identity.models import User
from backend.notifications.email import Email, EmailError, EmailSender
from backend.notifications.office import Office
from backend.notifications.texts import t
from backend.projects.models import Project, ProjectMember, ProjectSlug, ProjectStage
from backend.tenancy.models import Feature, Tenant
from backend.tenancy.resolve import known_features
from backend.web.page_stages import _title

log = logging.getLogger(__name__)

QUIET = timedelta(minutes=5)  # after the latest comment
HOLD = timedelta(minutes=30)  # after the first, however many follow
GIVE_UP = timedelta(days=1)  # still failing: logged, and not tried again
QUOTED = 300  # characters of each comment the email quotes
_TEMPLATES = Path(__file__).parent.parent / "notifications" / "templates"
_TEMPLATE = Template((_TEMPLATES / "comments.html").read_text("utf-8"))


async def _recipients(db: AsyncSession, project: Project, members: bool) -> list[str]:
    """The project's members, with that feature on and some chosen; else every
    staff account of the office (never a support session's)."""
    staff = select(User.email).where(User.support.is_(False))
    if members:
        chosen = list(
            await db.scalars(
                staff.join(ProjectMember, ProjectMember.user_id == User.id).where(
                    ProjectMember.project_id == project.id
                )
            )
        )
        if chosen:
            return sorted(chosen)
    return sorted(await db.scalars(staff))


async def _where(db: AsyncSession, comment: Comment, office: Office) -> str:
    """The stage ("01 Briefing") or the file ("Planta.pdf") it is on."""
    if comment.stage_id is None:
        return comment.item_name or ""
    stage = await db.get(ProjectStage, comment.stage_id)
    return f"{stage.position:02d} {await _title(db, stage, office.locale)}"


async def deliver(
    db: AsyncSession, sender: EmailSender, office: Office, project: Project, now: datetime
) -> int:
    """Email the office about its new client comments, if due, or again an email
    that failed for some address; how many emails went. The caller commits."""
    untold = (
        select(Comment)
        .where(
            Comment.project_id == project.id,
            Comment.author == Author.CLIENT,
            Comment.staff_notified_at.is_(None),
        )
        .order_by(Comment.created_at, Comment.id)
    )
    # An email already begun goes again as it was, removed comments and all.
    pending = list(await db.scalars(untold.where(Comment.alert_batch.is_not(None))))
    batch = pending[0].alert_batch if pending else None
    pending = [c for c in pending if c.alert_batch == batch]
    if not pending:
        pending = list(
            await db.scalars(
                untold.where(Comment.alert_batch.is_(None), Comment.removed_at.is_(None))
            )
        )
    if not pending:
        return 0
    features = known_features((await db.get(Tenant, project.tenant_id)).features)
    if Feature.COMMENTS not in features:
        for comment in pending:  # switched off meanwhile: never news later
            comment.staff_notified_at = now
        return 0
    if batch is None:
        if now - pending[-1].created_at < QUIET and now - pending[0].created_at < HOLD:
            return 0
        batch = uuid.uuid4()
        for comment in pending:
            comment.alert_batch = batch
    recipients = await _recipients(db, project, Feature.PROJECT_MEMBERS in features)
    slug = await db.scalar(
        select(ProjectSlug.slug).where(ProjectSlug.project_id == project.id, ProjectSlug.is_current)
    )
    link = f"{office.base}/{slug}"
    lines = []
    for comment in pending:
        quoted = comment.body if len(comment.body) <= QUOTED else comment.body[:QUOTED] + "…"
        where = await _where(db, comment, office)
        who = t(office.locale, "commentFrom", name=comment.author_name, where=where)
        lines.append((who, quoted))
    html, text = _render(office, project, link, lines)
    subject = t(office.locale, "commentsSubject", count=len(pending), project=project.name)
    sent, failed = 0, False
    for to in recipients:
        try:
            await sender.send(
                Email(
                    sender=office.sender,
                    to=to,
                    subject=subject,
                    html=html,
                    text=text,
                    # The address hashed: Resend keeps keys in its logs.
                    idempotency_key=f"comments-{batch.hex}-{hashlib.sha256(to.encode()).hexdigest()[:24]}",
                    reply_to=office.reply_to,
                )
            )
            sent += 1
        except EmailError as error:
            failed = True
            # AGENTS.md: the detail in the log at ERROR, with office and operation.
            log.error(
                "comments: emailing staff of %s/%s failed: %s",
                project.tenant_id,
                project.id,
                error.detail,
            )
    if failed and now - pending[0].created_at < GIVE_UP:
        return sent  # tried again next pass; those already sent aren't sent twice
    if failed:
        log.error("comments: giving up emailing staff of %s/%s", project.tenant_id, project.id)
    for comment in pending:
        comment.staff_notified_at = now
    return sent


def _render(
    office: Office, project: Project, link: str, lines: list[tuple[str, str]]
) -> tuple[str, str]:
    """The email as HTML (inline styles: email programs ignore stylesheets) and as
    plain text: who commented where, and what, quoted."""
    locale = office.locale
    intro = t(locale, "commentsIntro", project=project.name)
    why = t(locale, "commentsWhy", office=office.name)
    header = (
        f'<img src="{escape(office.logo_url)}" alt="{escape(office.name)}" height="40" '
        'style="height:40px;max-width:200px;display:block">'
        if office.logo_url
        else f'<strong style="font-size:18px">{escape(office.name)}</strong>'
    )
    body = "".join(
        f'<p style="margin:0 0 4px;font-size:14px;color:#66686b">{escape(who)}</p>'
        f'<p style="margin:0 0 16px;padding-left:12px;border-left:3px solid #e2e2de;'
        f'white-space:pre-wrap">{escape(said)}</p>'
        for who, said in lines
    )
    html = _TEMPLATE.substitute(
        lang=locale.value,
        header=header,
        intro=escape(intro),
        body=body,
        link=escape(link),
        open=escape(t(locale, "open")),
        why=escape(why),
    )
    text = "\n".join(
        [
            office.name,
            "",
            intro,
            "",
            *(f"{who}\n“{said}”\n" for who, said in lines),
            f"{t(locale, 'open')}: {link}",
            "",
            why,
        ]
    )
    return html, text
