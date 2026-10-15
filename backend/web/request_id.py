"""A short ID per request, in the `X-Request-ID` response header and every log line.

On Cloud Run the ID is Google's trace ID (from `X-Cloud-Trace-Context`), so Cloud
Logging groups all lines of one request. It is also the reference code users can
send us when something fails (AGENTS.md, "User-facing errors").
"""

from __future__ import annotations

import contextvars
import logging
import re
import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
_TRACE = re.compile(r"^([0-9a-f]{32})(?:/|$)")


def current_request_id() -> str:
    return _request_id.get()


class RequestIdLogFilter(logging.Filter):
    """Adds `record.request_id` to every log record ("-" outside a request)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id.get()
        return True


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        trace = _TRACE.match(Headers(scope=scope).get("x-cloud-trace-context", ""))
        request_id = trace.group(1) if trace else uuid.uuid4().hex
        token = _request_id.set(request_id)

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            _request_id.reset(token)
