"""The emails with a link to choose a password: a reset ("Esqueceu a senha?")
and an invite to the office's painel (A36); the one with a code to confirm an
email (joining through the office's shared link, or a changed address); and the
notice to the old address when an account's email changes.

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
_CONFIRM = Template((Path(__file__).parent / "templates" / "confirm.html").read_text("utf-8"))


def _header(office: Office) -> str:
    return (
        f'<img src="{escape(office.logo_url)}" alt="{escape(office.name)}" height="40" '
        'style="height:40px;max-width:200px;display:block">'
        if office.logo_url
        else f'<strong style="font-size:18px">{escape(office.name)}</strong>'
    )


def link_email(
    office: Office, to: str, token: str, *, texts: str, subject: str, hello: str, intro: str
) -> Email:
    """An email whose point is the one-time link to choose a password: a reset, or
    an invite (`texts`: the prefix of its button, expiry and ignore lines)."""
    locale = office.locale
    link = f"{office.base}{links.PATH}#token={token}"
    header = _header(office)
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


def invite_email(office: Office, name: str, to: str, token: str, inviter: str) -> Email:
    """An owner's invite to the office's painel (A36)."""
    locale = office.locale
    intro = t(locale, "inviteIntro", inviter=inviter, office=office.name)
    return link_email(
        office,
        to,
        token,
        texts="invite",
        subject=t(locale, "inviteSubject", office=office.name),
        hello=t(locale, "resetHello", name=_first(name)),
        intro=intro,
    )


def confirm_email(office: Office, name: str, to: str, token: str, code: str) -> Email:
    """The code to type where they signed up, or a link that confirms it here."""
    locale = office.locale
    link = f"{office.base}{links.CONFIRM_PATH}#token={token}"
    texts = {
        key: t(locale, f"confirm{key[0].upper()}{key[1:]}", office=office.name)
        for key in ("intro", "orLink", "button", "expiry", "ignore")
    }
    hello = t(locale, "resetHello", name=_first(name))
    html = _CONFIRM.substitute(
        lang=locale.value,
        header=_header(office),
        hello=escape(hello),
        code=escape(code),
        link=escape(link),
        **{key: escape(value) for key, value in texts.items()},
    )
    text = "\n".join(
        [
            office.name,
            "",
            hello,
            texts["intro"],
            "",
            code,
            "",
            f"{texts['orLink']} {link}",
            "",
            texts["expiry"],
            texts["ignore"],
        ]
    )
    return Email(
        sender=office.sender,
        to=to,
        subject=t(locale, "confirmSubject", code=code, office=office.name),
        html=html,
        text=text,
        idempotency_key="confirm-" + hashlib.sha256(token.encode()).hexdigest()[:32],
        reply_to=office.reply_to,
    )


def email_changed_email(office: Office, name: str, to: str, new: str) -> Email:
    """To the old address, when the account's email changes ("Minha conta"): so
    an unexpected change gets noticed. No link: nothing to do if it was them."""
    locale = office.locale
    hello = t(locale, "resetHello", name=_first(name))
    intro = t(locale, "emailChangedIntro", office=office.name, email=new)
    ignore = t(locale, "emailChangedIgnore")
    html = (
        f'<!doctype html><html lang="{locale.value}"><body style="font-family:Arial,sans-serif;'
        f'color:#1d1d1f;line-height:1.5">{_header(office)}<p>{escape(hello)}</p>'
        f"<p>{escape(intro)}</p><p>{escape(ignore)}</p></body></html>"
    )
    return Email(
        sender=office.sender,
        to=to,
        subject=t(locale, "emailChangedSubject", office=office.name),
        html=html,
        text="\n".join([office.name, "", hello, intro, "", ignore]),
        idempotency_key="email-changed-" + hashlib.sha256(f"{to}>{new}".encode()).hexdigest()[:32],
        reply_to=office.reply_to,
    )
