"""A client signing up for a project's emails from its page (A32, 20 Oct 2026): the
welcome email, saying they're in, with a small "Não foi você?" link to stop them
(the same unsubscribe link every update has)."""

from __future__ import annotations

import secrets
from html import escape
from pathlib import Path
from string import Template

from backend.notifications.email import Email
from backend.notifications.office import Office
from backend.notifications.texts import t

_TEMPLATE = Template((Path(__file__).parent / "templates" / "welcome.html").read_text("utf-8"))


def welcome_email(office: Office, project: str, page: str, to: str, unsubscribe: str) -> Email:
    locale = office.locale
    header = (
        f'<img src="{escape(office.logo_url)}" alt="{escape(office.name)}" height="40" '
        'style="height:40px;max-width:200px;display:block">'
        if office.logo_url
        else f'<strong style="font-size:18px">{escape(office.name)}</strong>'
    )
    hello = t(locale, "welcomeHello")
    intro = t(locale, "welcomeIntro", project=project, office=office.name)
    button, not_you, stop = (
        t(locale, key) for key in ("welcomeButton", "welcomeNotYou", "welcomeStop")
    )
    html = _TEMPLATE.substitute(
        lang=locale.value,
        header=header,
        hello=escape(hello),
        intro=escape(intro),
        page=escape(page),
        button=escape(button),
        notYou=escape(not_you),
        unsubscribe=escape(unsubscribe),
        stop=escape(stop),
    )
    text = "\n".join(
        [
            office.name,
            "",
            hello,
            intro,
            "",
            f"{button}: {page}",
            "",
            f"{not_you} {stop}: {unsubscribe}",
        ]
    )
    return Email(
        sender=office.sender,
        to=to,
        subject=t(locale, "welcomeSubject", project=project),
        html=html,
        text=text,
        # Each signing up its own (one back after unsubscribing gets a new welcome).
        idempotency_key=f"welcome-{secrets.token_hex(16)}",
        reply_to=office.reply_to,
        # The email program's own "unsubscribe" button too, as the updates have.
        headers={
            "List-Unsubscribe": f"<{unsubscribe}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
    )
