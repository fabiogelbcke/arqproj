"""A fresh database for the staff app's browser tests (`make e2e`).

    uv run python -m backend.commands.e2e

Drops and recreates `arqproj_e2e` on this machine, migrates it, gives the app's
login its access and adds the two fictional offices. Only ever local: the
browser tests start the real app against it, as the restricted login.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from backend.commands import local_db
from backend.commands.provision import provision_url
from backend.commands.seed import seed
from backend.settings import LOCAL_MIGRATION_DATABASE_URL, LOCAL_RUNTIME_ROLE

DATABASE = "arqproj_e2e"
OWNER_URL = make_url(LOCAL_MIGRATION_DATABASE_URL).set(database=DATABASE).render_as_string(False)
APP_URL = make_url(OWNER_URL).set(username=LOCAL_RUNTIME_ROLE).render_as_string(False)


async def _seed() -> None:
    engine = create_async_engine(OWNER_URL)
    async with AsyncSession(engine) as session:
        await seed(session)
        await session.commit()
    await engine.dispose()


def main() -> int:
    local_db.drop_database(DATABASE)
    local_db.create_database(DATABASE)
    local_db.require_local_server(OWNER_URL)  # before any migration
    local_db.create_runtime_role(LOCAL_RUNTIME_ROLE)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.attributes["database_url"] = OWNER_URL
    command.upgrade(config, "head")
    provision_url(OWNER_URL, LOCAL_RUNTIME_ROLE)
    asyncio.run(_seed())
    print(f"Ready: {DATABASE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
