"""Two fictional offices for local development.

    uv run python -m backend.tenancy.seed

Then open http://alinea.localhost:8000/ and http://norte.localhost:8000/ (browsers
send every *.localhost address to this machine). Safe to run repeatedly. Only
ever writes to a local database. Real addresses (alineaarquitetos.com, the
staging host) are added to staging and production in step 1.7, not here.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from backend.db import local
from backend.settings import Settings
from backend.tenancy.models import Tenant, TenantDomain

OFFICES = [
    {
        "slug": "alinea",
        "name": "Alinea (dev)",
        "domains": [("alinea.localhost", True), ("alinea-old.localhost", False)],
    },
    {
        "slug": "norte",
        "name": "Estúdio Norte (dev)",
        "domains": [("norte.localhost", True)],
    },
]


async def seed(session: AsyncSession) -> list[str]:
    """Create any missing offices and addresses. Returns what was added."""
    added = []
    for spec in OFFICES:
        tenant = await session.scalar(select(Tenant).where(Tenant.slug == spec["slug"]))
        if tenant is None:
            tenant = Tenant(slug=spec["slug"], name=spec["name"])
            session.add(tenant)
            added.append(f"office {spec['slug']}")
        for hostname, primary in spec["domains"]:
            exists = await session.scalar(
                select(TenantDomain.id).where(TenantDomain.hostname == hostname)
            )
            if exists is None:
                session.add(TenantDomain(tenant=tenant, hostname=hostname, is_primary=primary))
                added.append(f"address {hostname}")
    await session.commit()
    return added


async def main() -> None:
    # Offices are created by the owner: the app's own login can only read them.
    url = Settings().migration_database_url
    local.require_local(url)
    engine = create_async_engine(url)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        await local.require_local_server(session)
        added = await seed(session)
    await engine.dispose()
    print("Added: " + ", ".join(added) if added else "Nothing to add; already seeded.")


if __name__ == "__main__":
    asyncio.run(main())
