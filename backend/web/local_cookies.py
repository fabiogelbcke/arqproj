"""Keeps the cookies of local copies of the app, running on different ports, apart.

Browsers ignore the port when they store cookies, so every copy on
`alinea.localhost` would share one `portal_session`: signing in to one signs out
of the others, whose databases don't know its session. Locally, each cookie is
stored in the browser under a name carrying the port in the address bar, and the
app itself sees the usual names. Never installed on a deployed app, whose address
has no port.
"""

from __future__ import annotations

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


def _port(host: str) -> str | None:
    port = host.rpartition(":")[2]
    return port if ":" in host and port.isdigit() else None


def _own_cookies(header: str, suffix: str) -> str:
    """This port's cookies, under the names the app knows."""
    own = []
    for cookie in header.split(";"):
        name, separator, value = cookie.strip().partition("=")
        if name.endswith(suffix):
            own.append(f"{name.removesuffix(suffix)}{separator}{value}")
    return "; ".join(own)


class LocalCookiesMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        port = _port(Headers(scope=scope).get("host", "")) if scope["type"] == "http" else None
        if port is None:
            await self.app(scope, receive, send)
            return
        suffix = f"__{port}"
        headers = MutableHeaders(scope=scope)
        if "cookie" in headers:
            headers["cookie"] = _own_cookies(headers["cookie"], suffix)

        async def send_with_own_names(message: Message) -> None:
            if message["type"] == "http.response.start":
                answer = MutableHeaders(scope=message)
                cookies = answer.getlist("set-cookie")
                del answer["set-cookie"]
                for cookie in cookies:
                    name, _, rest = cookie.partition("=")
                    answer.append("set-cookie", f"{name}{suffix}={rest}")
            await send(message)

        await self.app(scope, receive, send_with_own_names)
