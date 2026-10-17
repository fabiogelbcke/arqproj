"""The maintenance pass, for the scheduler (A09, A19, A32).

    POST /internal/maintenance   new files on published pages, then due emails

Cloud Scheduler calls it every 10 minutes with a Google-signed ID token for its
own service account. The site is public, so the app checks the token itself:
signed by Google, meant for this service (`MAINTENANCE_AUDIENCE`), from the
scheduler's account (`MAINTENANCE_CALLER`). Anything else gets a 404, as if
nothing were here. Without those settings (locally) the address doesn't exist;
`uv run python -m backend.commands.maintenance` runs the same pass.

One pass is bounded work (section 4); two at once skip each other's projects
(backend/notifications/scan.py).
"""

from __future__ import annotations

import logging
from dataclasses import asdict

import anyio
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from backend.notifications.email import sender_for
from backend.notifications.scan import run_maintenance

log = logging.getLogger(__name__)
router = APIRouter(include_in_schema=False)

# Cloud Run and the scheduler give a request 300 seconds: no new project starts
# after 240, leaving a minute for the one under way (each Drive call may take 30).
BUDGET_SECONDS = 240


def _verify(token: str, audience: str) -> dict:
    """The token's claims, if Google signed it for `audience`; ValueError if not."""
    from google.auth.transport.requests import Request as GoogleRequest
    from google.oauth2 import id_token

    return id_token.verify_oauth2_token(token, GoogleRequest(), audience)


@router.post("/internal/maintenance")
async def maintenance(request: Request) -> Response:
    settings = request.app.state.settings
    if not (settings.maintenance_audience and settings.maintenance_caller):
        return Response(status_code=404)
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        return Response(status_code=404)
    try:
        claims = await anyio.to_thread.run_sync(_verify, token, settings.maintenance_audience)
    except ValueError as error:
        # Only the kind: google-auth's messages can quote the token itself.
        log.warning("maintenance: refused a token (%s)", type(error).__name__)
        return Response(status_code=404)
    if claims.get("email") != settings.maintenance_caller or not claims.get("email_verified"):
        log.warning("maintenance: refused a token from %s", claims.get("email"))
        return Response(status_code=404)
    report = await run_maintenance(
        request.app.state.sessionmaker,
        settings,
        getattr(request.app.state, "google", None),
        sender_for(settings, request.app.state.http),
        budget=BUDGET_SECONDS,
    )
    if report.unfinished:
        log.warning(
            "maintenance: out of time, %s projects left for the next pass", report.unfinished
        )
    return JSONResponse(asdict(report))
