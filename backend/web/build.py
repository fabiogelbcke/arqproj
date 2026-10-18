"""Every response says which build served it (`X-Build-Id`).

An open painel tab keeps running the build it loaded. When it sees a different
build ID from the API, it offers to reload (plan A30).
"""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

HEADER = "X-Build-Id"


class BuildIdMiddleware:
    def __init__(self, app: ASGIApp, build_id: str) -> None:
        self.app = app
        self.build_id = build_id

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_build(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[HEADER] = self.build_id
            await send(message)

        await self.app(scope, receive, send_with_build)
