"""Login sessions stored in the database.

The browser holds a random token; only its SHA-256 hash is stored, so a copy of
the database cannot be used to sign in. Sessions are tenant rows: one from another
tenant is invisible, so a cookie only works on the address it was issued for.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.identity.models import LoginSession, User

LIFETIME = timedelta(days=30)  # since last use
# Last use is written at most this often, not on every request.
TOUCH_EVERY = timedelta(hours=1)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


async def start(session: AsyncSession, user: User) -> tuple[str, LoginSession]:
    """Create a session; returns the token for the cookie (never stored) and the row."""
    token = secrets.token_urlsafe(32)
    row = LoginSession(
        user_id=user.id,
        token_hash=_hash(token),
        csrf_token=secrets.token_urlsafe(32),
        expires_at=_now() + LIFETIME,
    )
    session.add(row)
    await session.flush()
    return token, row


async def find_active(session: AsyncSession, token: str) -> tuple[LoginSession, User] | None:
    """The live session for this token and its user, extending it if due."""
    now = _now()
    found = (
        await session.execute(
            select(LoginSession, User)
            .join(User, User.id == LoginSession.user_id)
            .where(
                LoginSession.token_hash == _hash(token),
                LoginSession.revoked_at.is_(None),
                LoginSession.expires_at > now,
            )
        )
    ).first()
    if found is None:
        return None
    row, user = found
    if now - row.last_seen_at >= TOUCH_EVERY:
        row.last_seen_at = now
        row.expires_at = now + LIFETIME
        await session.flush()
    return row, user


async def revoke(session: AsyncSession, row: LoginSession) -> None:
    row.revoked_at = _now()
    await session.flush()
