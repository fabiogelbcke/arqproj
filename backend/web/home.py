"""Public product home for visitors and Google's OAuth consent screen.

Like the legal pages, it needs neither a tenant nor a signed-in session.
Only the two named assets are served; this is not a general file server.
The example project (plan section 16) is served here too: its content is in the
client page's bundle, so its page is the same on Unio's address, which the home
links to, and on every office's.
"""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, PlainTextResponse, Response

from backend.projects.enums import EXAMPLE_SLUG
from backend.web.painel import CONTENT_SECURITY_POLICY, SHELL_CACHE

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


@router.get(f"/{EXAMPLE_SLUG}")
def example(request: Request) -> Response:
    shell = Path(request.app.state.settings.frontend_dist) / "client.html"
    if not shell.is_file():
        return PlainTextResponse(
            "The client page is not built. Run `make build` (or `make dev`).", status_code=503
        )
    # The page names itself once drawn, after the office whose address it is on.
    head = '<title>Projeto de exemplo</title>\n    <meta name="robots" content="noindex" />'
    document = shell.read_text("utf-8").replace("<!--page-head-->", head)
    return Response(
        document,
        media_type="text/html; charset=utf-8",
        headers={
            "Cache-Control": SHELL_CACHE,
            "Content-Security-Policy": CONTENT_SECURITY_POLICY,
            "X-Robots-Tag": "noindex",
        },
    )
