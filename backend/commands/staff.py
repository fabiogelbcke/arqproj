"""Create staff accounts and password links. Run by an owner of the deployment.

    uv run python -m backend.commands.staff add --tenant alinea --email ana@x.com --name Ana
    uv run python -m backend.commands.staff owner-link --tenant alinea
    uv run python -m backend.commands.staff reset-link --tenant alinea --email ana@x.com
    uv run python -m backend.commands.staff reset-tour --tenant alinea --email ana@x.com

Nobody types someone else's password: `add` creates the account without one and
prints an invite link, `reset-link` prints a link to choose a new one, and
`owner-link` lets the recipient supply their own name, email and password.
Send the printed link to the person. Connects as the owner
(MIGRATION_DATABASE_URL) and scopes everything to the given tenant, so it works
under row-level security like the app. Account rules live in the runtime code
(`backend.identity.accounts`, `backend.identity.links`), shared with the painel.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import secrets
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from backend.db.isolation import scope_to_tenant
from backend.identity import accounts, links
from backend.identity.models import JoinLink, LinkKind, Role
from backend.settings import Settings
from backend.tenancy.models import Tenant, TenantDomain


async def run(argv: list[str], database_url: str) -> str:
    parser = argparse.ArgumentParser(prog="backend.commands.staff")
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("add", help="create a staff account and print an invite link")
    add.add_argument("--tenant", required=True, help="tenant slug, e.g. alinea")
    add.add_argument("--email", required=True)
    add.add_argument("--name", required=True)
    add.add_argument("--role", default=Role.MEMBER, choices=list(Role), type=Role)
    owner = commands.add_parser("owner-link", help="print a one-time owner signup link")
    owner.add_argument("--tenant", required=True)
    owner.add_argument("--days", type=int, default=7)
    reset = commands.add_parser("reset-link", help="print a link to choose a new password")
    reset.add_argument("--tenant", required=True)
    reset.add_argument("--email", required=True)
    tour = commands.add_parser("reset-tour", help="show the project page's tour again")
    tour.add_argument("--tenant", required=True)
    tour.add_argument("--email", required=True)
    args = parser.parse_args(argv)
    if args.command == "owner-link" and args.days < 1:
        parser.error("--days must be at least 1")

    engine = create_async_engine(database_url)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            tenant_id, host = (
                await session.execute(
                    select(Tenant.id, TenantDomain.hostname)
                    .outerjoin(
                        TenantDomain,
                        (TenantDomain.tenant_id == Tenant.id) & TenantDomain.is_primary,
                    )
                    .where(Tenant.slug == args.tenant)
                )
            ).first() or (None, None)
            if tenant_id is None:
                raise SystemExit(f"No tenant {args.tenant!r}")
            if host is None:
                raise SystemExit(f"Tenant {args.tenant!r} has no primary address for the link")
            await session.commit()  # the next transaction starts scoped to the tenant
            scope_to_tenant(session.sync_session, tenant_id)
            if args.command == "owner-link":
                token = secrets.token_urlsafe(32)
                session.add(
                    JoinLink(
                        role=Role.OWNER,
                        single_use=True,
                        expires_at=datetime.now(UTC) + timedelta(days=args.days),
                        token_hash=hashlib.sha256(token.encode()).hexdigest(),
                    )
                )
                await session.commit()
                link = links.url(host, token, path="/painel/entrar-na-equipe")
                return (
                    f"Owner signup for {args.tenant}. Send them this link "
                    f"(works once, for {args.days} day(s)):\n{link}"
                )
            try:
                if args.command == "add":
                    user = await accounts.create_user(
                        session, email=args.email, name=args.name, role=args.role
                    )
                    token = await links.create(session, user, LinkKind.INVITE)
                    done = f"Created {user.role} {user.email} in {args.tenant}"
                else:
                    user = await accounts.find_user(session, args.email)
                    if user is None:
                        raise accounts.AccountError(f"No account for {args.email.strip().lower()}")
                    if args.command == "reset-tour":
                        # For trying the first-visit tour again, here or on staging.
                        user.tour_seen_at = None
                        await session.commit()
                        return f"The tour starts again on {user.email}'s next project page."
                    token = await links.create(session, user, LinkKind.RESET)
                    done = f"Reset link for {user.email} in {args.tenant}"
            except accounts.AccountError as error:
                raise SystemExit(str(error)) from None
            await session.commit()
    finally:
        await engine.dispose()
    kind = LinkKind.INVITE if args.command == "add" else LinkKind.RESET
    days = links.LIFETIME[kind].days
    return f"{done}. Send them this link (works once, for {days} day(s)):\n{links.url(host, token)}"


def main() -> int:
    url = Settings().migration_database_url
    print(asyncio.run(run(sys.argv[1:], url)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
