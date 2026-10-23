"""Liveness check for Cloud Run and uptime monitoring.

The path is `/health`, not `/healthz`: Cloud Run's front end answers `/healthz`
(and `/statusz`) itself, so they never reach the app there.
"""

import logging

from fastapi import APIRouter

logger = logging.getLogger("backend.posthog.logs")
router = APIRouter()


@router.get("/health", include_in_schema=False)
def health() -> dict[str, str]:
    logger.info("health check completed")
    return {"status": "ok"}
