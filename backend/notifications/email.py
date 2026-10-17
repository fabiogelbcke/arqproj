"""Sending an email: Resend when a key is configured, else a local folder (A17).

The batching and the email's content know nothing of the provider; changing it
means another `EmailSender`. Each email carries an idempotency key, so a retry
after a timeout or a crash never sends it twice (Resend keeps keys for 24 hours).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import httpx2

from backend.settings import Settings

log = logging.getLogger(__name__)

RESEND_URL = "https://api.resend.com/emails"
# Resend's test sender: delivers only to the Resend account's own address, which
# is all staging needs until a domain is verified.
RESEND_TEST_SENDER = "onboarding@resend.dev"


@dataclass(frozen=True)
class Email:
    sender: str  # "Name <address>"
    to: str
    subject: str
    html: str
    text: str
    idempotency_key: str
    reply_to: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


class EmailError(Exception):
    """Sending failed. `detail` is for the log (AGENTS.md), never for a screen."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class EmailSender(Protocol):
    async def send(self, email: Email) -> str:
        """The provider's id for the email."""
        ...


class ResendSender:
    def __init__(self, http: httpx2.AsyncClient, api_key: str) -> None:
        self._http = http
        self._headers = {"Authorization": f"Bearer {api_key}"}

    async def send(self, email: Email) -> str:
        body = {
            "from": email.sender,
            "to": [email.to],
            "subject": email.subject,
            "html": email.html,
            "text": email.text,
            "headers": email.headers,
        }
        if email.reply_to:
            body["reply_to"] = email.reply_to
        try:
            response = await self._http.post(
                RESEND_URL,
                json=body,
                headers=self._headers | {"Idempotency-Key": email.idempotency_key},
            )
        except httpx2.TransportError as error:
            raise EmailError(f"resend: {error!r}") from error
        if response.status_code >= 400:
            # Never the request: it holds the key.
            raise EmailError(f"resend {response.status_code}: {response.text[:300]}")
        return response.json().get("id", "")


class OutboxSender:
    """Local development: each email becomes an .html file to open in a browser
    (and a .txt beside it). Nothing leaves the machine."""

    def __init__(self, folder: Path) -> None:
        self._folder = folder

    async def send(self, email: Email) -> str:
        self._folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        name = re.sub(r"[^a-zA-Z0-9@._-]+", "-", f"{stamp}-{email.to}-{email.idempotency_key}")
        path = self._folder / f"{name}.html"
        meta = "".join(
            f"<!-- {k}: {v} -->\n"
            for k, v in [
                ("From", email.sender),
                ("To", email.to),
                ("Reply-To", email.reply_to or ""),
                ("Subject", email.subject),
                *email.headers.items(),
            ]
        )
        path.write_text(meta + email.html, encoding="utf-8")
        path.with_suffix(".txt").write_text(email.text, encoding="utf-8")
        log.info("email written to %s", path)
        return f"outbox:{path.name}"


def sender_for(settings: Settings, http: httpx2.AsyncClient) -> EmailSender:
    if settings.resend_api_key:
        return ResendSender(http, settings.resend_api_key)
    if settings.deployed:
        # Deployed without a key would silently send nothing: say so loudly.
        raise RuntimeError("RESEND_API_KEY must be set in staging and production")
    return OutboxSender(Path(settings.email_outbox))
