"""Liveness check for Cloud Run and uptime monitoring.

The path is `/health`, not `/healthz`: Cloud Run's front end intercepts paths
ending in "z", so `/healthz` never reaches the app there.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health", include_in_schema=False)
def health() -> dict[str, str]:
    return {"status": "ok"}
