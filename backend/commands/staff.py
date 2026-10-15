"""Create staff accounts and set passwords. Run by an owner of the deployment.

    uv run python -m backend.commands.staff add --tenant alinea --email ana@x.com --name Ana
    uv run python -m backend.commands.staff set-password --tenant alinea --email ana@x.com

Prompts for the password, so it never lands in shell history. Connects as the
owner (MIGRATION_DATABASE_URL) and scopes everything to the given tenant, so it
works under row-level security like the app. Account rules live in the runtime
code (`backend.identity.accounts`), shared with a future sign-up page.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from backend.db.isolation import scope_to_tenant
from backend.identity import accounts
from backend.settings import Settings
from backend.tenancy.models import Tenant


def _ask_password() -> str:
    first = getpass.getpass("Password: ")
    if first != getpass.getpass("Password again: "):
        raise SystemExit("The passwords do not match")
    return first


async def run(argv: list[str], database_url: str, ask_password: Callable[[], str]) -> str:
    parser = argparse.ArgumentParser(prog="backend.commands.staff")
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("add", help="create a staff account")
    add.add_argument("--tenant", required=True, help="tenant slug, e.g. alinea")
    add.add_argument("--email", required=True)
    add.add_argument("--name", required=True)
    add.add_argument("--role", default="member", choices=["owner", "member"])
    reset = commands.add_parser("set-password", help="set a new password")
    reset.add_argument("--tenant", required=True)
    reset.add_argument("--email", required=True)
    args = parser.parse_args(argv)

    engine = create_async_engine(database_url)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            tenant_id = await session.scalar(select(Tenant.id).where(Tenant.slug == args.tenant))
            if tenant_id is None:
                raise SystemExit(f"No tenant {args.tenant!r}")
            await session.commit()  # the next transaction starts scoped to the tenant
            scope_to_tenant(session.sync_session, tenant_id)
            try:
                if args.command == "add":
                    user = await accounts.create_user(
                        session,
                        email=args.email,
                        name=args.name,
                        role=args.role,
                        password=ask_password(),
                    )
                    message = f"Created {user.role} {user.email} in {args.tenant}"
                else:
                    user = await accounts.set_password(session, args.email, ask_password())
                    message = f"Password set for {user.email} in {args.tenant}"
            except accounts.AccountError as error:
                raise SystemExit(str(error)) from None
            await session.commit()
    finally:
        await engine.dispose()
    return message


def main() -> int:
    url = Settings().migration_database_url
    print(asyncio.run(run(sys.argv[1:], url, _ask_password)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
