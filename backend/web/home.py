"""Public product home for visitors and Google's OAuth consent screen.

Like the legal pages, it needs neither a tenant nor a signed-in session.
Only the two named assets are served; this is not a general file server.
"""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(include_in_schema=False)
PUBLIC = Path(__file__).with_name("public")
HEADERS = {
    "Cache-Control": "public, max-age=3600",
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'self'; img-src 'self'; "
        "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}


@router.api_route("/", methods=["GET", "HEAD"])
def home() -> FileResponse:
    return FileResponse(PUBLIC / "index.html", media_type="text/html", headers=HEADERS)


@router.api_route("/brand/landing.css", methods=["GET", "HEAD"])
def stylesheet() -> FileResponse:
    return FileResponse(PUBLIC / "landing.css", media_type="text/css", headers=HEADERS)


@router.api_route("/brand/unio.png", methods=["GET", "HEAD"])
def logo() -> FileResponse:
    return FileResponse(PUBLIC / "unio.png", media_type="image/png", headers=HEADERS)
