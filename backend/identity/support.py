"""Support access (A43): an operator enters an office as its owner or a member.

Each office has up to two hidden "Suporte Unio" accounts, one per role, made the
first time an operator enters with that role. They have no password, an address
no mail reaches, and `support` set, which keeps them out of every other way in
(`accounts.find_user`) and out of the team, counts and notices.

The operator dashboard makes a one-time link (`links`, kind `support`, 2 minutes)
on Unio's own host; the operator's browser opens it on the office's address,
which spends it and starts a session that lasts an hour and is never extended.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.identity import links
from backend.identity.models import LinkKind, Role, User

NAME = "Suporte Unio"
LIFETIME = timedelta(hours=1)
PATH = "/painel/suporte"


def address(role: Role) -> str:
    # `.invalid` is reserved (RFC 2606): no mail is ever delivered there.
    return f"suporte-{role.value}@unio.invalid"


async def account(session: AsyncSession, role: Role) -> User:
    """The office's support account for `role`, made the first time."""
    user = await session.scalar(select(User).where(User.support, User.role == role))
    if user is None:
        user = User(email=address(role), name=NAME, role=role, password_hash=None, support=True)
        session.add(user)
        await session.flush()
    return user


async def entry_link(session: AsyncSession, role: Role, host: str) -> str:
    """A one-time link that signs the browser that opens it in as `role`'s account."""
    token = await links.create(session, await account(session, role), LinkKind.SUPPORT)
    return links.url(host, token, path=PATH)


async def use(session: AsyncSession, token: str) -> User | None:
    """Spend an entry link: its support account, or None."""
    user = await links.use(session, token, (LinkKind.SUPPORT,))
    return user if user is not None and user.support else None
