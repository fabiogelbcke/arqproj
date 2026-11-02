"""Sending WhatsApp messages (A44): Meta's Cloud API when configured, else a
local folder beside the emails.

A message a client didn't just ask for (an update, the welcome, the staff's
question) must be a template Meta approved beforehand: Meta holds its fixed text
and we send only the parts that change. `text` is the message as the client
reads it, kept for the outbox and the logs. A reply to something the client
wrote (SAIR, "Quero receber") is free text, allowed for 24 hours after it.

Meta has no idempotency key: a message counts as sent once Meta accepts it.
"""

from __future__ import annotations

import hmac
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import httpx2

from backend.security import keys
from backend.settings import Environment, Settings
from backend.tenancy.models import Locale

log = logging.getLogger(__name__)

GRAPH_URL = "https://graph.facebook.com/{version}/{number}/messages"
# The templates' names at Meta, and their languages there.
UPDATE_TEMPLATE = "unio_atualizacao"
WELCOME_TEMPLATE = "unio_boas_vindas"
INVITE_TEMPLATE = "unio_convite"
LANGUAGES = {Locale.PT_BR: "pt_BR", Locale.EN: "en"}
PHONE_MAX = 40  # a number as typed, with its spaces and punctuation
# Meta's error for a number that has no WhatsApp.
NOT_ON_WHATSAPP = 131026
# A part that changes in a template: no line breaks, tabs or runs of spaces
# (Meta's rule), and short enough to keep the message whole.
PARAM_MAX = 600


# -- numbers --------------------------------------------------------------------------


def parse_phone(raw: str) -> str | None:
    """A number as typed, in international digits (5511912345678), or None.

    A Brazilian mobile may be typed with or without +55 and punctuation; any
    other country needs its + and country code."""
    text = raw.strip()
    digits = re.sub(r"\D", "", text)
    if text.startswith("+") or text.startswith("00"):
        digits = digits.removeprefix("00") if text.startswith("00") else digits
        if digits.startswith("55"):
            return _brazilian(digits[2:])
        return digits if re.fullmatch(r"[1-9]\d{7,14}", digits) else None
    if len(digits) == 13 and digits.startswith("55"):
        digits = digits[2:]
    return _brazilian(digits.removeprefix("0"))


def _brazilian(national: str) -> str | None:
    """A mobile: two-digit area code (no 0), then 9 and eight digits."""
    if re.fullmatch(r"[1-9][1-9]9\d{8}", national):
        return "55" + national
    return None


def canonical(wa_id: str) -> str:
    """The number Meta reports a message from, as we store numbers. Some
    Brazilian accounts are reported without the mobile's leading 9."""
    if re.fullmatch(r"55[1-9][1-9][6-9]\d{7}", wa_id):
        return wa_id[:4] + "9" + wa_id[4:]
    return wa_id


def opt_out_hash(settings: Settings, phone: str) -> str:
    """How a number that replied SAIR is kept: not the number itself."""
    return keys.keyed_hash(settings.app_secret, "whatsapp-opt-out", phone)


def may_receive(settings: Settings, phone: str) -> bool:
    """Outside production, only `WHATSAPP_TEST_NUMBERS` get real messages (plan
    section 14, as emails go only to staff). Written to the outbox, anyone."""
    if settings.environment is Environment.PRODUCTION or not settings.whatsapp_token:
        return True
    return phone in settings.whatsapp_test_list


def param(text: str) -> str:
    """A template's changing part as Meta accepts it."""
    flat = re.sub(r"\s+", " ", text).strip()
    return flat if len(flat) <= PARAM_MAX else flat[: PARAM_MAX - 1].rstrip() + "…"


# -- tokens Meta hands back -----------------------------------------------------------
#
# A button's payload and a message's callback data come back in Meta's webhook,
# which belongs to no office: they say which office and which number they are
# about, signed so they can't be made up. Short: Meta limits their length.


@dataclass(frozen=True)
class Token:
    action: str  # "yes" or "no" (the question's buttons), "sent" (a message's status)
    tenant_id: uuid.UUID
    recipient_id: uuid.UUID


def _mac(settings: Settings, body: str) -> str:
    return keys.keyed_hash(settings.app_secret, "whatsapp-token", body)[:20]


def token(settings: Settings, action: str, tenant_id: uuid.UUID, recipient_id: uuid.UUID) -> str:
    body = f"{action}.{tenant_id.hex}.{recipient_id.hex}"
    return f"{body}.{_mac(settings, body)}"


def read_token(settings: Settings, value: str) -> Token | None:
    try:
        action, tenant, recipient, mac = value.split(".")
        if not hmac.compare_digest(mac, _mac(settings, f"{action}.{tenant}.{recipient}")):
            return None
        return Token(action, uuid.UUID(hex=tenant), uuid.UUID(hex=recipient))
    except (ValueError, TypeError):
        return None


# -- sending --------------------------------------------------------------------------


@dataclass(frozen=True)
class WhatsAppMessage:
    to: str
    text: str  # as the client reads it
    template: str | None = None  # None: a free-text reply
    language: str = "pt_BR"
    params: tuple[str, ...] = ()  # the template's body parts, in order
    buttons: tuple[str, ...] = ()  # the template's quick-reply payloads, in order
    callback: str | None = None  # comes back with the message's delivery status


class WhatsAppError(Exception):
    """Sending failed. `detail` is for the log (AGENTS.md), never for a screen."""

    def __init__(self, detail: str, code: int | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.code = code  # Meta's error code, when it gave one


class WhatsAppSender(Protocol):
    async def send(self, message: WhatsAppMessage) -> str:
        """Meta's id for the message."""
        ...


def request_body(message: WhatsAppMessage) -> dict:
    body: dict = {"messaging_product": "whatsapp", "to": message.to}
    if message.template is None:
        body |= {"type": "text", "text": {"body": message.text}}
    else:
        components: list[dict] = []
        if message.params:
            components.append(
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": p} for p in message.params],
                }
            )
        for index, payload in enumerate(message.buttons):
            components.append(
                {
                    "type": "button",
                    "sub_type": "quick_reply",
                    "index": str(index),
                    "parameters": [{"type": "payload", "payload": payload}],
                }
            )
        body |= {
            "type": "template",
            "template": {
                "name": message.template,
                "language": {"code": message.language},
                "components": components,
            },
        }
    if message.callback:
        body["biz_opaque_callback_data"] = message.callback
    return body


class CloudApiSender:
    def __init__(self, http: httpx2.AsyncClient, settings: Settings) -> None:
        self._http = http
        self._url = GRAPH_URL.format(
            version=settings.whatsapp_api_version, number=settings.whatsapp_phone_number_id
        )
        self._headers = {"Authorization": f"Bearer {settings.whatsapp_token}"}

    async def send(self, message: WhatsAppMessage) -> str:
        try:
            response = await self._http.post(
                self._url, json=request_body(message), headers=self._headers
            )
        except httpx2.TransportError as error:
            raise WhatsAppError(f"whatsapp: {error!r}") from error
        if response.status_code >= 400:
            code = None
            try:
                code = response.json().get("error", {}).get("code")
            except ValueError:
                pass
            # Never the request: it holds the number and the token is in its headers.
            raise WhatsAppError(f"whatsapp {response.status_code}: {response.text[:300]}", code)
        messages = response.json().get("messages") or [{}]
        return messages[0].get("id", "")


class OutboxWhatsAppSender:
    """Local development: each message becomes a .txt file in the emails' outbox,
    as the client would read it. Nothing leaves the machine."""

    def __init__(self, folder: Path) -> None:
        self._folder = folder

    async def send(self, message: WhatsAppMessage) -> str:
        self._folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
        path = self._folder / f"{stamp}-whatsapp-{message.to}.txt"
        meta = [
            f"To: +{message.to}",
            f"Template: {message.template or '(free-text reply)'}",
            *(f"Button {i + 1} payload: {b}" for i, b in enumerate(message.buttons)),
        ]
        path.write_text("\n".join([*meta, "", message.text, ""]), encoding="utf-8")
        log.info("whatsapp message written to %s", path)
        return f"outbox:{path.name}"


def whatsapp_sender_for(
    settings: Settings, http: httpx2.AsyncClient | None
) -> WhatsAppSender | None:
    """None where WhatsApp isn't set up: deployed without Meta's settings, nothing
    is sent (offices only have WhatsApp once the operator switches it on, A40)."""
    if settings.whatsapp_token and settings.whatsapp_phone_number_id and http is not None:
        return CloudApiSender(http, settings)
    if settings.deployed:
        return None
    return OutboxWhatsAppSender(Path(settings.email_outbox))
