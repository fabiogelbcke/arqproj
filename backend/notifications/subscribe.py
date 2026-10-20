"""A client asking for a project's emails from its page (A32, 20 Oct 2026): the
email with the link that confirms the address is theirs, and the link's token.

The token holds the project, the address and an expiry, encrypted (the address
stays out of request logs) and never stored: confirming twice changes nothing.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from html import escape
from pathlib import Path
from string import Template

from backend.notifications.email import Email
from backend.notifications.office import Office
from backend.notifications.texts import t
from backend.security import keys
from backend.settings import Settings

PURPOSE = "subscribe"
LIFETIME_SECONDS = 7 * 24 * 3600
# The same simple layout as the password emails.
_TEMPLATE = Template((Path(__file__).parent / "templates" / "reset.html").read_text("utf-8"))


def subscribe_token(settings: Settings, project_id: uuid.UUID, email: str) -> str:
    plain = json.dumps({"p": str(project_id), "e": email, "x": int(time.time()) + LIFETIME_SECONDS})
    return keys.encrypt(settings.app_secret, PURPOSE, plain)


def subscribing(settings: Settings, token: str) -> tuple[uuid.UUID, str] | None:
    """The project and the address, while the link lasts."""
    try:
        found = json.loads(keys.decrypt(settings.app_secret, PURPOSE, token))
        if int(found["x"]) < time.time():
            return None
        return uuid.UUID(found["p"]), str(found["e"])
    except (keys.BadToken, ValueError, KeyError, TypeError):
        return None


def confirm_email(office: Office, project: str, to: str, token: str) -> Email:
    locale = office.locale
    link = f"{office.base}/api/emails/subscribe/{token}"
    header = (
        f'<img src="{escape(office.logo_url)}" alt="{escape(office.name)}" height="40" '
        'style="height:40px;max-width:200px;display:block">'
        if office.logo_url
        else f'<strong style="font-size:18px">{escape(office.name)}</strong>'
    )
    hello = t(locale, "subscribeHello")
    intro = t(locale, "subscribeIntro", project=project, office=office.name)
    button, expiry, ignore = (
        t(locale, f"subscribe{part}") for part in ("Button", "Expiry", "Ignore")
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
        subject=t(locale, "subscribeSubject", project=project),
        html=html,
        text=text,
        idempotency_key="subscribe-" + hashlib.sha256(token.encode()).hexdigest()[:32],
        reply_to=office.reply_to,
    )
