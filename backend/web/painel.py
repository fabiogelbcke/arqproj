"""The staff app (painel): the React build in `frontend/dist`, served at /painel.

Every `/painel/...` page address returns the same app shell, and the app's router
picks the screen, so deep links and reloads work. The shell is never cached: it
names the current build's files. Those files (`/painel/assets/...`) have content
fingerprints in their names, so browsers may keep them for a year.

The shell carries no data and makes no authorization decisions (plan section 17):
the app asks the API who is signed in.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, PlainTextResponse, Response

PREFIX = "/painel"
ASSETS = f"{PREFIX}/assets/"
SHELL_CACHE = "no-cache"
ASSET_CACHE = "public, max-age=31536000, immutable"
# Plan section 4: scripts and styles only from this site. Everything the app loads
# is its own build and its own API; it is never framed (clickjacking).
CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        # Plus exactly one inline style: React Aria's fixed touch-action rule for
        # pressable elements (usePress). Any other inline style stays blocked; if
        # a library update changes that rule, `make e2e` fails on the violation.
        "style-src 'self' 'sha256-38RhXrc7EdReTKsOm23ZPOCUgniTUUcjky8QOOrQx6o='",
        # blob: previews a photo chosen on this device before it is uploaded.
        "img-src 'self' data: blob:",
        "font-src 'self'",
        # Uploads go from the browser straight to Google's upload session (A31).
        "connect-src 'self' https://www.googleapis.com",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
)

router = APIRouter(include_in_schema=False)


def _dist(request: Request) -> Path:
    return Path(request.app.state.settings.frontend_dist)


@router.get(PREFIX + "/assets/{name:path}")
async def asset(name: str, request: Request) -> Response:
    root = (_dist(request) / "assets").resolve()
    path = (root / name).resolve()
    # Only files inside assets/: never `..` out of it, and a missing file is a
    # plain 404, not the shell (a stale tab asking for an old build's file must
    # fail visibly so the app can offer a reload).
    if not path.is_relative_to(root) or not path.is_file():
        return PlainTextResponse("Not found", status_code=404)
    return FileResponse(path, headers={"Cache-Control": ASSET_CACHE})


@router.get(PREFIX)
@router.get(PREFIX + "/{page:path}")
async def shell(request: Request, page: str = "") -> Response:
    index = _dist(request) / "index.html"
    if not index.is_file():
        return PlainTextResponse(
            "The staff app is not built. Run `make build` (or `make dev` for development).",
            status_code=503,
        )
    return FileResponse(
        index,
        headers={"Cache-Control": SHELL_CACHE, "Content-Security-Policy": CONTENT_SECURITY_POLICY},
    )
