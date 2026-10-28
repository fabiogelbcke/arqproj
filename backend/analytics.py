"""Product analytics (A39): sending events to PostHog from a request.

Staff events go through the request's PostHog context (`app.PostHogContextMiddleware`),
which already carries the office and, once `web.auth` has looked up the session, the
signed-in person. Visitor events (clients, suppliers, anyone with a share link) are
personless: they carry an anonymous id that changes every day, so distinct visitors
can be counted but no one can be followed from one day to the next, and nothing is
stored. Without PostHog configured (everywhere but production) nothing is sent.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import UTC, datetime

from fastapi import Request

from backend.security.keys import keyed_hash
from backend.web.attempts import device as address

log = logging.getLogger(__name__)

_TABLET = re.compile(r"iPad|Tablet", re.I)
_PHONE = re.compile(r"iPhone|Android.+Mobile|Windows Phone", re.I)


def capture(request: Request, event: str, properties: dict | None = None) -> None:
    """A staff action, as this request's person and office."""
    client = getattr(request.app.state, "posthog", None)
    if client is not None:
        client.capture(event, properties=properties or {})


def device_kind(user_agent: str) -> str:
    """ "phone", "tablet" or "computer", from the browser's User-Agent."""
    if _TABLET.search(user_agent):
        return "tablet"
    if _PHONE.search(user_agent):
        return "phone"
    return "tablet" if "Android" in user_agent else "computer"  # Android without "Mobile"


def visitor_id(request: Request, today: datetime | None = None) -> str:
    """An anonymous id for today's visitor: a keyed hash of their address, browser
    and the date. The key comes from APP_SECRET, so it can't be recomputed outside
    the app; the date makes it change every day."""
    day = (today or datetime.now(UTC)).date().isoformat()
    seen = f"{day}|{address(request)}|{request.headers.get('user-agent', '')}"
    return keyed_hash(request.app.state.settings.app_secret, "analytics-visitor", seen)[:20]


def visitor_properties(request: Request, tenant_id: uuid.UUID) -> dict:
    """What every visitor event carries: personless, the office, the device."""
    tenant = getattr(request.state, "tenant", None)
    return {
        "$process_person_profile": False,
        "$groups": {"tenant": str(tenant_id)},
        "tenant": tenant.slug if tenant is not None else None,
        "device": device_kind(request.headers.get("user-agent", "")),
    }


def capture_visit(
    request: Request, tenant_id: uuid.UUID, event: str, properties: dict | None = None
) -> None:
    """Something a client or other visitor did. Never fails the request."""
    client = getattr(request.app.state, "posthog", None)
    if client is None:
        return
    try:
        client.capture(
            event,
            distinct_id=f"visitor:{visitor_id(request)}",
            properties=visitor_properties(request, tenant_id) | (properties or {}),
        )
    except Exception:
        log.exception("analytics: %s failed for tenant %s", event, tenant_id)
