"""One maintenance pass, by hand: `uv run python -m backend.commands.maintenance`.

The same pass the scheduler will call every 10 minutes (A09, A32): files shown
for the first time on published projects' pages (A10), then the client emails
that are due (A12). Without RESEND_API_KEY the emails are written to
local-test-data/outbox to open in a browser. Runs as the app's login, like the
app, so office isolation applies.
"""

from __future__ import annotations

import asyncio

import httpx2

from backend.db.engine import create_engine, create_sessionmaker
from backend.notifications.email import sender_for
from backend.notifications.scan import run_maintenance
from backend.settings import Settings
from backend.storage.google import GoogleDriveStorage, ServerIdentity


async def main() -> None:
    settings = Settings()
    engine = create_engine(settings)
    try:
        async with httpx2.AsyncClient(timeout=30) as http:
            google = GoogleDriveStorage(ServerIdentity(), http)
            sender = sender_for(settings, http)
            report = await run_maintenance(create_sessionmaker(engine), settings, google, sender)
    finally:
        await engine.dispose()
    print(report)


if __name__ == "__main__":
    asyncio.run(main())
