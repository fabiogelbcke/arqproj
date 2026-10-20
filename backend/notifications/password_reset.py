"""The emails with a link to choose a password: a reset ("Esqueceu a senha?")
and an invite to the office's painel (A36).

Sent from the office's address, in its language, with the link on its own
address (never one taken from the request: plan section 4). The link works once
and for a day (backend.identity.links).
"""

from __future__ import annotations

import hashlib
from html import escape
from pathlib import Path
from string import Template

from backend.identity import links
from backend.notifications.email import Email
from backend.notifications.office import Office
from backend.notifications.texts import t

_TEMPLATE = Template((Path(__file__).parent / "templates" / "reset.html").read_text("utf-8"))


def link_email(
    office: Office, to: str, token: str, *, texts: str, subject: str, hello: str, intro: str
) -> Email:
    """An email whose point is the one-time link to choose a password: a reset, or
    an invite (`texts`: the prefix of its button, expiry and ignore lines)."""
    locale = office.locale
    link = f"{office.base}{links.PATH}#token={token}"
    header = (
        f'<img src="{escape(office.logo_url)}" alt="{escape(office.name)}" height="40" '
        'style="height:40px;max-width:200px;display:block">'
        if office.logo_url
        else f'<strong style="font-size:18px">{escape(office.name)}</strong>'
    )
    button, expiry, ignore = (
        t(locale, f"{texts}{part}") for part in ("Button", "Expiry", "Ignore")
    )
    html = _TEMPLATE.substitute(
        lang=locale.value,
        header=header,
        hello=escape(hello),
        intro=escape(intro),
        link=escape(link),
        button=escape(button),
        expiry=escape(expiry),
        ignore=escape(ignore),
    )
    text = "\n".join([office.name, "", hello, intro, "", f"{button}: {link}", "", expiry, ignore])
    return Email(
        sender=office.sender,
        to=to,
        subject=subject,
        html=html,
        text=text,
        # One email per link, however often a retry sends it.
        idempotency_key=f"{texts}-" + hashlib.sha256(token.encode()).hexdigest()[:32],
        reply_to=office.reply_to,
    )


def _first(name: str) -> str:
    return name.split()[0] if name.split() else name


def reset_email(office: Office, name: str, to: str, token: str) -> Email:
    return link_email(
        office,
        to,
        token,
        texts="reset",
        subject=t(office.locale, "resetSubject", office=office.name),
        hello=t(office.locale, "resetHello", name=_first(name)),
        intro=t(office.locale, "resetIntro", office=office.name),
    )


def invite_email(office: Office, name: str, to: str, token: str, inviter: str | None) -> Email:
    """An invite to the office's painel (A36): from an owner, or asked for through
    the office's shared link (no inviter)."""
    locale = office.locale
    intro = (
        t(locale, "inviteIntro", inviter=inviter, office=office.name)
        if inviter
        else t(locale, "inviteIntroLink", office=office.name)
    )
    return link_email(
        office,
        to,
        token,
        texts="invite",
        subject=t(locale, "inviteSubject", office=office.name),
        hello=t(locale, "resetHello", name=_first(name)),
        intro=intro,
    )
