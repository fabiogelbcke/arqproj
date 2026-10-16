"""One maintenance pass, by hand: `uv run python -m backend.commands.maintenance`.

The same pass the scheduler will call every 10 minutes (A09, A32): for now it
records files shown for the first time on published projects' pages (A10). Runs
as the app's login, like the app, so office isolation applies.
"""

from __future__ import annotations

import asyncio

import httpx2

from backend.db.engine import create_engine, create_sessionmaker
from backend.notifications.scan import run_maintenance
from backend.settings import Settings
from backend.storage.google import GoogleDriveStorage, ServerIdentity


async def main() -> None:
    settings = Settings()
    engine = create_engine(settings)
    try:
        async with httpx2.AsyncClient(timeout=30) as http:
            google = GoogleDriveStorage(ServerIdentity(), http)
            report = await run_maintenance(create_sessionmaker(engine), settings, google)
    finally:
        await engine.dispose()
    print(report)


if __name__ == "__main__":
    asyncio.run(main())
