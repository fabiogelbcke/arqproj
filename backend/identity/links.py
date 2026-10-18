"""One-time links for choosing a password: invites for new accounts, resets.

Staff choose their own passwords; nobody else ever knows them. Whoever creates
the account (the `staff` command now, an office owner in the painel later) gets a
link to pass on. The token travels in the URL fragment (`#token=`), which
browsers never send to the server, so it stays out of request logs.

Like sessions, only a hash of the token is stored, a link is a tenant row (so it
only works on its own office's address), it works once, and it expires.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.identity.models import LinkKind, PasswordLink, User

LIFETIME = {LinkKind.INVITE: timedelta(days=7), LinkKind.RESET: timedelta(days=1)}
PATH = "/painel/definir-senha"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


LOCAL_PORT = 5173  # `make dev`'s staff app; with `make serve` it is 8000


def url(host: str, token: str) -> str:
    # Local addresses (*.localhost) are plain http on the dev server's port.
    base = f"http://{host}:{LOCAL_PORT}" if host.endswith(".localhost") else f"https://{host}"
    return f"{base}{PATH}#token={token}"


async def create(session: AsyncSession, user: User, kind: LinkKind) -> str:
    """A new link for `user`; any earlier unused link of theirs stops working."""
    await session.execute(
        delete(PasswordLink).where(PasswordLink.user_id == user.id, PasswordLink.used_at.is_(None))
    )
    token = secrets.token_urlsafe(32)
    session.add(
        PasswordLink(
            user_id=user.id,
            kind=kind,
            token_hash=_hash(token),
            expires_at=datetime.now(UTC) + LIFETIME[kind],
        )
    )
    await session.flush()
    return token


def _usable(token: str):
    return (
        PasswordLink.token_hash == _hash(token),
        PasswordLink.used_at.is_(None),
        PasswordLink.expires_at > func.now(),
    )


async def find(session: AsyncSession, token: str) -> tuple[PasswordLink, User] | None:
    """The usable link for this token and its account, without using it up."""
    found = (
        await session.execute(
            select(PasswordLink, User)
            .join(User, User.id == PasswordLink.user_id)
            .where(*_usable(token))
        )
    ).first()
    return (found[0], found[1]) if found else None


async def use(session: AsyncSession, token: str) -> User | None:
    """Spend the link and return its account. A single UPDATE, so two requests
    racing with the same link cannot both succeed."""
    user_id = await session.scalar(
        update(PasswordLink)
        .where(*_usable(token))
        .values(used_at=func.now())
        .returning(PasswordLink.user_id)
    )
    return None if user_id is None else await session.get(User, user_id)
