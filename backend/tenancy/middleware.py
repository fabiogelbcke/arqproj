"""Attach the tenant to every request, or answer before routing.

- Unknown host or suspended tenant: plain 404 (never a default tenant).
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

from backend.tenancy.resolve import normalize_host, resolve

# The maintenance pass is every office's: called by the scheduler, never a page.
# Unio's public home, its assets and legal pages belong to no office (A33).
EXEMPT_PATHS = frozenset(
    {
        "/",
        "/brand/landing.css",
        "/brand/unio.png",
        "/health",
        "/api/docs",
        "/api/openapi.json",
        "/internal/maintenance",
        "/privacidade",
        "/termos",
    }
)
# The staff app's built files are the same for every tenant: no lookup per file.
EXEMPT_PREFIXES = ("/painel/assets/",)
# Google's shared return address is no office's: let it through without a tenant
# (backend/web/drive.py forwards it to the office that started).
UNOWNED_PATHS = frozenset({"/api/drive/callback"})
# The operator dashboard (A38) belongs to no office: on Unio's own address
# (OPERATOR_HOST) these pass without one, even where that address also serves an
# office (staging's). Anywhere else they go on as usual, and answer 404.
OPERATOR_PAGE = "/admin"
OPERATOR_PATHS = frozenset({OPERATOR_PAGE, "/api/auth/google/callback"})
OPERATOR_PREFIXES = (OPERATOR_PAGE + "/", "/api/admin/")


def operator_path(path: str) -> bool:
    return path in OPERATOR_PATHS or path.startswith(OPERATOR_PREFIXES)


REDIRECT_MAX_AGE = 86400  # one day


class TenantMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope["type"] != "http" or path in EXEMPT_PATHS or path.startswith(EXEMPT_PREFIXES):
            await self.app(scope, receive, send)
            return

        state = scope["app"].state
        host = Headers(scope=scope).get("host")
        if operator_path(path) and normalize_host(host) == state.settings.operator_host:
            await self.app(scope, receive, send)
            return
        async with state.sessionmaker() as session:
            resolution = await resolve(session, host)

        if resolution is None:
            if path in UNOWNED_PATHS:
                await self.app(scope, receive, send)
                return
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

        scope.setdefault("state", {})["tenant"] = resolution.tenant
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
