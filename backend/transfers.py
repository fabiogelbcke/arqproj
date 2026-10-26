"""Aggregate transfer telemetry, without file names, URLs or visitor identities."""

import logging
from contextlib import aclosing

log = logging.getLogger(__name__)


async def measured(request, project, chunks, source: str):
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
            tenant = getattr(request.state, "tenant", None)
            try:
                client.capture(
                    "file_transfer",
                    distinct_id=f"tenant:{project.tenant_id}",
                    properties={
                        "$process_person_profile": False,
                        "$groups": {"tenant": str(project.tenant_id)},
                        "tenant": tenant.slug if tenant else None,
                        "source": source,
                        "bytes": sent,
                        "complete": complete,
                    },
                )
            except Exception:
                # Analytics must never turn a successful download into a failure.
                log.exception("transfer telemetry failed: tenant=%s", project.tenant_id)
