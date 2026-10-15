"""Attach the office to every request, or answer before routing.

- Unknown host or suspended office: plain 404 (never a default office).
- Alias or `www.`: permanent redirect to the primary host, same path and query,
  remembered by browsers for a day so a later change of primary takes effect.
- Exempt paths (health check, local API docs) skip this entirely.

Written as plain ASGI middleware rather than BaseHTTPMiddleware, so it never
buffers streamed responses such as file downloads.
"""

from __future__ import annotations

from starlette.datastructures import Headers
from starlette.responses import PlainTextResponse, RedirectResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from backend.tenancy.resolve import resolve

EXEMPT_PATHS = frozenset({"/health", "/api/docs", "/api/openapi.json"})
REDIRECT_MAX_AGE = 86400  # one day


class OfficeMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return

        state = scope["app"].state
        host = Headers(scope=scope).get("host")
        async with state.sessionmaker() as session:
            resolution = await resolve(session, host)

        if resolution is None:
            await PlainTextResponse("Not found", status_code=404)(scope, receive, send)
            return
        if resolution.redirect_host:
            target = _redirect_url(scope, host, resolution.redirect_host, state.settings.deployed)
            # 301 for page loads; 308 keeps a POST a POST.
            status = 301 if scope["method"] in ("GET", "HEAD") else 308
            response = RedirectResponse(
                target,
                status_code=status,
                headers={"Cache-Control": f"public, max-age={REDIRECT_MAX_AGE}"},
            )
            await response(scope, receive, send)
            return

        scope.setdefault("state", {})["office"] = resolution.office
        await self.app(scope, receive, send)


def _redirect_url(
    scope: Scope, requested_host: str | None, target_host: str, deployed: bool
) -> str:
    # Deployed traffic always arrives over HTTPS at Google's front end, even though
    # the app itself sees plain HTTP. Locally, keep the scheme and the dev port.
    scheme = "https" if deployed else scope.get("scheme", "http")
    port = ""
    if not deployed and requested_host and ":" in requested_host.rsplit("]", 1)[-1]:
        port = ":" + requested_host.rsplit(":", 1)[1]
    query = scope.get("query_string", b"").decode("latin-1")
    path = scope.get("raw_path", scope["path"].encode()).decode("latin-1")
    return f"{scheme}://{target_host}{port}{path}" + (f"?{query}" if query else "")
