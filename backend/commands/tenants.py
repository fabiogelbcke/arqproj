"""Create offices (tenants) and their addresses. Run by an owner of the deployment.

    uv run python -m backend.commands.tenants add --slug alinea --name "ALINEA ARQUITETOS" \\
        --host portal-staging-496714293251.us-east1.run.app
    uv run python -m backend.commands.tenants add-host --slug alinea --host alinea.example --primary

Connects as the owner (MIGRATION_DATABASE_URL); `make tenant ENV=staging ...`
reaches staging through the Cloud SQL Auth Proxy. The local seed
(`backend.commands.seed`) stays for local databases only.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from backend.settings import Settings
from backend.tenancy.models import Locale, Tenant, TenantDomain
from backend.tenancy.resolve import normalize_host


def _host(raw: str) -> str:
    # A bare address only: a pasted URL or port is refused, not silently trimmed
    # into something that would never match a request.
    if any(sign in raw for sign in (":", "/")):
        raise SystemExit(f"Not a usable address: {raw!r} (no scheme, port, path or www.)")
    host = normalize_host(raw)
    if not host or host.startswith("www."):
        raise SystemExit(f"Not a usable address: {raw!r} (no scheme, port or www.)")
    return host


async def run(argv: list[str], database_url: str) -> str:
    parser = argparse.ArgumentParser(prog="backend.commands.tenants")
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("add", help="create an office with its primary address")
    add.add_argument("--slug", required=True)
    add.add_argument("--name", required=True)
    add.add_argument("--host", required=True, help="primary address, e.g. alinea.example.com")
    add.add_argument("--locale", default=Locale.PT_BR, choices=list(Locale), type=Locale)
    add.add_argument("--timezone", default="America/Sao_Paulo")
    more = commands.add_parser("add-host", help="add an address to an office")
    more.add_argument("--slug", required=True)
    more.add_argument("--host", required=True)
    more.add_argument("--primary", action="store_true", help="make it the primary address")
    args = parser.parse_args(argv)
    host = _host(args.host)

    engine = create_async_engine(database_url)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            if await session.scalar(select(TenantDomain.id).where(TenantDomain.hostname == host)):
                raise SystemExit(f"{host} already belongs to an office")
            existing = await session.scalar(select(Tenant).where(Tenant.slug == args.slug))
            if args.command == "add":
                if existing is not None:
                    raise SystemExit(f"There is already an office {args.slug!r}")
                tenant = Tenant(
                    slug=args.slug, name=args.name, locale=args.locale, timezone=args.timezone
                )
                session.add(tenant)
                await session.flush()
                session.add(TenantDomain(tenant_id=tenant.id, hostname=host, is_primary=True))
                message = f"Created office {args.slug} on {host}"
            else:
                if existing is None:
                    raise SystemExit(f"No office {args.slug!r}")
                if args.primary:
                    await session.execute(
                        update(TenantDomain)
                        .where(TenantDomain.tenant_id == existing.id)
                        .values(is_primary=False)
                    )
                session.add(
                    TenantDomain(tenant_id=existing.id, hostname=host, is_primary=args.primary)
                )
                kind = "primary address" if args.primary else "address"
                message = f"Added {kind} {host} to {args.slug}"
            await session.commit()
    finally:
        await engine.dispose()
    return message


def main() -> int:
    print(asyncio.run(run(sys.argv[1:], Settings().migration_database_url)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
