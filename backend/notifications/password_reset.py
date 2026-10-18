"""The email with a link to choose a new password ("Esqueceu a senha?").

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


def reset_email(office: Office, name: str, to: str, token: str) -> Email:
    locale = office.locale
    link = f"{office.base}{links.PATH}#token={token}"
    hello = t(locale, "resetHello", name=name.split()[0] if name.split() else name)
    intro = t(locale, "resetIntro", office=office.name)
    header = (
        f'<img src="{escape(office.logo_url)}" alt="{escape(office.name)}" height="40" '
        'style="height:40px;max-width:200px;display:block">'
        if office.logo_url
        else f'<strong style="font-size:18px">{escape(office.name)}</strong>'
    )
    html = _TEMPLATE.substitute(
        lang=locale.value,
        header=header,
        hello=escape(hello),
        intro=escape(intro),
        link=escape(link),
        button=escape(t(locale, "resetButton")),
        expiry=escape(t(locale, "resetExpiry")),
        ignore=escape(t(locale, "resetIgnore")),
    )
    text = "\n".join(
        [
            office.name,
            "",
            hello,
            intro,
            "",
            f"{t(locale, 'resetButton')}: {link}",
            "",
            t(locale, "resetExpiry"),
            t(locale, "resetIgnore"),
        ]
    )
    return Email(
        sender=office.sender,
        to=to,
        subject=t(locale, "resetSubject", office=office.name),
        html=html,
        text=text,
        # One email per link, however often a retry sends it.
        idempotency_key="reset-" + hashlib.sha256(token.encode()).hexdigest()[:32],
        reply_to=office.reply_to,
    )
