"""Meta's WhatsApp webhook (A47): what clients answer, and what became of our messages.

    GET  /api/whatsapp/webhook   Meta checks the address when it is registered
    POST /api/whatsapp/webhook   messages and delivery statuses

It belongs to no office (one Unio number serves them all): registered once at
Meta as https://myunio.app/api/whatsapp/webhook. Meta signs each request with
the app's secret; anything unsigned gets a 404, as if nothing were here.

- "Quero receber" / "Não quero": the question's buttons carry a signed token
  naming the office and the number's row, which they subscribe or decline.
- SAIR (PARAR, CANCELAR, STOP): no more WhatsApp updates from any project.
- Anything else: one automatic reply a day saying nobody reads this number.
- A message Meta couldn't deliver because the number has no WhatsApp marks that
  number unreachable, through the token our message carried.

Meta resends what doesn't get a 200: a message whose handling failed answers 500
so it comes again, and each message's id is recorded as handled in the same
transaction as what it changed, so one that comes again is handled once. An
answer Meta delivers late doesn't undo a SAIR the client sent after it.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import unicodedata
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import select

from backend.db.isolation import scope_to_tenant
from backend.notifications import whatsapp_updates
from backend.notifications.models import ProjectWhatsApp, WhatsAppStatus
from backend.notifications.whatsapp import (
    NOT_ON_WHATSAPP,
    WhatsAppError,
    canonical,
    forms,
    may_receive,
    read_token,
    whatsapp_sender_for,
)
from backend.projects.models import Project
from backend.tenancy.models import Locale, Tenant

log = logging.getLogger(__name__)
router = APIRouter(include_in_schema=False)

PATH = "/api/whatsapp/webhook"
STOP_WORDS = frozenset({"SAIR", "PARAR", "PARE", "CANCELAR", "STOP"})
AUTO_REPLY_EVERY = 24 * 3600  # one automatic reply a day per number
_auto_replied: dict[str, float] = {}  # per instance: at worst a reply more


def _signed(settings, body: bytes, header: str) -> bool:
    if not settings.whatsapp_app_secret or not header.startswith("sha256="):
        return False
    expected = hmac.new(settings.whatsapp_app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(header.removeprefix("sha256="), expected)


def _word(text: str) -> str:
    """ "  Sair! " → "SAIR": no accents, case or punctuation."""
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return "".join(c for c in plain if c.isalnum()).upper()


@router.get(PATH)
async def verify(request: Request) -> Response:
    settings = request.app.state.settings
    query = request.query_params
    if (
        settings.whatsapp_verify_token
        and query.get("hub.mode") == "subscribe"
        and hmac.compare_digest(query.get("hub.verify_token", ""), settings.whatsapp_verify_token)
    ):
        return PlainTextResponse(query.get("hub.challenge", ""))
    return Response(status_code=404)


@router.post(PATH)
async def webhook(request: Request) -> Response:
    settings = request.app.state.settings
    body = await request.body()
    if not _signed(settings, body, request.headers.get("x-hub-signature-256", "")):
        return Response(status_code=404)
    try:
        payload = json.loads(body)
    except ValueError:
        return Response(status_code=400)
    failed = False
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            for message in value.get("messages") or []:
                try:
                    await _message(request, message)
                except Exception:
                    failed = True
                    log.exception("whatsapp webhook: handling a message failed")
            for status in value.get("statuses") or []:
                try:
                    await _status(request, status)
                except Exception:
                    failed = True
                    log.exception("whatsapp webhook: handling a status failed")
    # Meta sends it all again: what was handled is skipped by its id.
    return Response(status_code=500 if failed else 200)


async def _send(request: Request, message) -> None:
    settings = request.app.state.settings
    sender = whatsapp_sender_for(settings, getattr(request.app.state, "http", None))
    if sender is None or not may_receive(settings, message.to):
        return
    try:
        await sender.send(message)
    except WhatsAppError as error:
        log.error("whatsapp webhook: replying failed: route=%s %s", PATH, error.detail)


def _sent_at(message: dict) -> datetime:
    """When the client sent it (Meta's Unix time), else now."""
    try:
        return datetime.fromtimestamp(int(message["timestamp"]), UTC)
    except (KeyError, TypeError, ValueError):
        return datetime.now(UTC)


async def _message(request: Request, message: dict) -> None:
    settings = request.app.state.settings
    phone = canonical(str(message.get("from", "")))
    message_id = str(message.get("id") or "")
    kind = message.get("type")
    payload = None
    if kind == "button":
        payload = (message.get("button") or {}).get("payload")
    elif kind == "interactive":
        payload = ((message.get("interactive") or {}).get("button_reply") or {}).get("id")
    found = read_token(settings, payload) if payload else None
    if found is not None and found.action in ("yes", "no"):
        await _answer(request, phone, found, message_id, _sent_at(message))
        return
    if kind == "text" and _word((message.get("text") or {}).get("body", "")) in STOP_WORDS:
        async with request.app.state.sessionmaker() as db:
            if not await whatsapp_updates.first_time(db, message_id):
                return
            for form in forms(phone):  # however it was typed where it was added
                await whatsapp_updates.opt_out(db, settings, form, _sent_at(message))
            await db.commit()
        log.info("whatsapp: a number replied SAIR")
        await _send(request, whatsapp_updates.reply(Locale.PT_BR, phone, "stopped"))
        return
    async with request.app.state.sessionmaker() as db:
        if not await whatsapp_updates.first_time(db, message_id):
            return
        await db.commit()
    now = time.monotonic()
    if now - _auto_replied.get(phone, -AUTO_REPLY_EVERY) >= AUTO_REPLY_EVERY:
        _auto_replied[phone] = now
        await _send(request, whatsapp_updates.reply(Locale.PT_BR, phone, "autoReply"))


async def _answer(request: Request, phone: str, found, message_id: str, sent_at: datetime) -> None:
    """ "Quero receber" or "Não quero", from the number the question went to."""
    settings = request.app.state.settings
    async with request.app.state.sessionmaker() as db:
        scope_to_tenant(db.sync_session, found.tenant_id)
        if not await whatsapp_updates.first_time(db, message_id):
            return
        recipient = await db.scalar(
            select(ProjectWhatsApp).where(ProjectWhatsApp.id == found.recipient_id)
        )
        if recipient is None or recipient.phone not in forms(phone):
            await db.commit()  # handled: nothing to change
            return  # removed by staff meanwhile, or not this number's button
        if recipient.answered_at is not None and sent_at <= recipient.answered_at:
            await db.commit()  # an older answer delivered late: the newer one stands
            return
        project = await db.scalar(select(Project).where(Project.id == recipient.project_id))
        locale = await db.scalar(select(Tenant.locale).where(Tenant.id == found.tenant_id))
        recipient.answered_at = sent_at
        if found.action == "yes":
            recipient.status = WhatsAppStatus.SUBSCRIBED
            # Their own choice lifts a SAIR sent before it, not one sent after.
            for form in forms(phone):
                await whatsapp_updates.opt_back_in(db, settings, form, sent_at)
        else:
            recipient.status = WhatsAppStatus.DECLINED
        await db.commit()
        name = project.name if project else ""
    log.info("whatsapp: a number answered %s for project %s", found.action, recipient.project_id)
    key = "accepted" if found.action == "yes" else "declined"
    await _send(request, whatsapp_updates.reply(locale or Locale.PT_BR, phone, key, project=name))


async def _status(request: Request, status: dict) -> None:
    if status.get("status") != "failed":
        return
    errors = status.get("errors") or [{}]
    code = errors[0].get("code")
    log.warning("whatsapp: Meta couldn't deliver a message: %s %s", code, errors[0].get("title"))
    found = read_token(request.app.state.settings, status.get("biz_opaque_callback_data") or "")
    if code != NOT_ON_WHATSAPP or found is None or found.action != "sent":
        return
    async with request.app.state.sessionmaker() as db:
        scope_to_tenant(db.sync_session, found.tenant_id)
        recipient = await db.scalar(
            select(ProjectWhatsApp).where(ProjectWhatsApp.id == found.recipient_id)
        )
        if recipient is not None:
            recipient.status = WhatsAppStatus.UNREACHABLE
            await db.commit()
