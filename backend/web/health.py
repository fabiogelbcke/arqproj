"""Liveness check for Cloud Run and uptime monitoring.

The path is `/health`, not `/healthz`: Cloud Run's front end answers `/healthz`
(and `/statusz`) itself, so they never reach the app there.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health", include_in_schema=False)
def health() -> dict[str, str]:
    return {"status": "ok"}
