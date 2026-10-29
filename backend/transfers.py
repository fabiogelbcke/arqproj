"""Aggregate transfer telemetry, without file names, URLs or visitor identities: a
visitor's download carries only the day's anonymous visitor id (backend.analytics)."""

import logging
from contextlib import aclosing

from backend.analytics import visitor_id, visitor_properties

log = logging.getLogger(__name__)


async def measured(request, project, chunks, source: str, *, staff: bool = False):
    sent = 0
    complete = False
    try:
        async with aclosing(chunks):
            async for chunk in chunks:
                sent += len(chunk)
                yield chunk
        complete = True
    finally:
        client = getattr(request.app.state, "posthog", None)
        if client is not None:
            try:
                client.capture(
                    "file_transfer",
                    distinct_id=(
                        f"tenant:{project.tenant_id}" if staff else f"visitor:{visitor_id(request)}"
                    ),
                    properties=visitor_properties(request, project.tenant_id)
                    | {
                        "viewer": "staff" if staff else "visitor",
                        "source": source,
                        "bytes": sent,
                        "complete": complete,
                    },
                )
            except Exception:
                # Analytics must never turn a successful download into a failure.
                log.exception("transfer telemetry failed: tenant=%s", project.tenant_id)
