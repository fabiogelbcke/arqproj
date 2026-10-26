"""Liveness check for Cloud Run and uptime monitoring.

The path is `/health`, not `/healthz`: Cloud Run's front end answers `/healthz`
(and `/statusz`) itself, so they never reach the app there.
"""

from fastapi import APIRouter

from backend.posthog_logs import log as posthog_log

router = APIRouter()


@router.get("/health", include_in_schema=False)
def health() -> dict[str, str]:
    posthog_log.info("health check served")
    return {"status": "ok"}
