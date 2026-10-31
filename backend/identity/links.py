"""One-time links for choosing a password (invites for new accounts, resets), and
for confirming an email (someone who joined through the office's shared link).

Staff choose their own passwords; nobody else ever knows them. Whoever creates
the account (the `staff` command now, an office owner in the painel later) gets a
link to pass on; for a reset, the app emails one ("Esqueceu a senha?"). The
token travels in the URL fragment (`#token=`), which browsers never send to the
server, so it stays out of request logs.

Like sessions, only a hash of the token is stored, a link is a tenant row (so it
only works on its own office's address), it works once, and it expires.

A confirmation also carries a 6-digit code, typed on the screen where the person
signed up (they often read the email on another device). It must be typed into
that account's own session, so someone who signs up with another person's address
gets nowhere: the code goes to that person. A few wrong codes use the link up.
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Collection
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.identity.models import LinkKind, PasswordLink, User

LIFETIME = {
    LinkKind.INVITE: timedelta(days=7),
    LinkKind.RESET: timedelta(days=1),
    LinkKind.CONFIRM: timedelta(days=1),
    # Opened at once, in the operator's own browser (A43).
    LinkKind.SUPPORT: timedelta(minutes=2),
}
PATH = "/painel/definir-senha"
CONFIRM_PATH = "/painel/confirmar-email"
CODE_TRIES = 5  # wrong codes before a confirmation link is used up
# The links for choosing a password; a confirmation never sets one.
PASSWORD_KINDS = (LinkKind.INVITE, LinkKind.RESET)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


LOCAL_PORT = 5173  # `make dev`'s staff app; with `make serve` it is 8000


def url(host: str, token: str, *, path: str = PATH) -> str:
    # Local addresses (*.localhost) are plain http on the dev server's port.
    base = f"http://{host}:{LOCAL_PORT}" if host.endswith(".localhost") else f"https://{host}"
    return f"{base}{path}#token={token}"


async def made_since(session: AsyncSession, user: User, kind: LinkKind, since: datetime) -> bool:
    """Whether `user` got a link of this kind after `since`, used or not."""
    found = await session.scalar(
        select(PasswordLink.id)
        .where(
            PasswordLink.user_id == user.id,
            PasswordLink.kind == kind,
            PasswordLink.created_at > since,
        )
        .limit(1)
    )
    return found is not None


async def create(session: AsyncSession, user: User, kind: LinkKind) -> str:
    """A new link for `user`; any earlier unused link of theirs stops working."""
    token = secrets.token_urlsafe(32)
    await _add(session, user, kind, token, code_hash=None)
    return token


async def create_confirmation(session: AsyncSession, user: User) -> tuple[str, str]:
    """A new confirmation for `user`'s email (any earlier unused link of theirs
    stops working): the link's token and its code."""
    token = secrets.token_urlsafe(32)
    code = f"{secrets.randbelow(10**6):06d}"
    await _add(session, user, LinkKind.CONFIRM, token, code_hash=_code_hash(_hash(token), code))
    return token, code


def _code_hash(token_hash: str, code: str) -> str:
    return _hash(f"{token_hash}:{code}")


async def _add(
    session: AsyncSession, user: User, kind: LinkKind, token: str, code_hash: str | None
) -> None:
    # Retired as if used (the app may mark links used, not delete them).
    await session.execute(
        update(PasswordLink)
        .where(PasswordLink.user_id == user.id, PasswordLink.used_at.is_(None))
        .values(used_at=func.now())
    )
    session.add(
        PasswordLink(
            user_id=user.id,
            kind=kind,
            token_hash=_hash(token),
            code_hash=code_hash,
            expires_at=datetime.now(UTC) + LIFETIME[kind],
        )
    )
    await session.flush()


def _live():
    return (PasswordLink.used_at.is_(None), PasswordLink.expires_at > func.now())


def _usable(token: str, kinds: Collection[LinkKind]):
    # A support account (A43) is entered only by its own kind of link: never one
    # that sets a password or confirms an email, however it came to exist.
    support = PasswordLink.user_id.in_(select(User.id).where(User.support))
    return (
        PasswordLink.token_hash == _hash(token),
        PasswordLink.kind.in_(kinds),
        support if set(kinds) == {LinkKind.SUPPORT} else ~support,
        *_live(),
    )


async def find(
    session: AsyncSession, token: str, kinds: Collection[LinkKind] = PASSWORD_KINDS
) -> tuple[PasswordLink, User] | None:
    """The usable link for this token and its account, without using it up."""
    found = (
        await session.execute(
            select(PasswordLink, User)
            .join(User, User.id == PasswordLink.user_id)
            .where(*_usable(token, kinds))
        )
    ).first()
    return (found[0], found[1]) if found else None


async def use(
    session: AsyncSession, token: str, kinds: Collection[LinkKind] = PASSWORD_KINDS
) -> User | None:
    """Spend the link and return its account. A single UPDATE, so two requests
    racing with the same link cannot both succeed."""
    user_id = await session.scalar(
        update(PasswordLink)
        .where(*_usable(token, kinds))
        .values(used_at=func.now())
        .returning(PasswordLink.user_id)
    )
    return None if user_id is None else await session.get(User, user_id)


class CodeResult(StrEnum):
    RIGHT = "right"  # the link is used up: the email is confirmed
    WRONG = "wrong"  # another try is left
    EXPIRED = "expired"  # no usable confirmation (expired, used, or too many wrong codes)


async def use_code(session: AsyncSession, user: User, code: str) -> CodeResult:
    """Check a code typed by `user` against their current confirmation."""
    link = await session.scalar(
        select(PasswordLink).where(
            PasswordLink.user_id == user.id, PasswordLink.kind == LinkKind.CONFIRM, *_live()
        )
    )
    if link is None or link.code_hash is None:
        return CodeResult.EXPIRED
    if secrets.compare_digest(link.code_hash, _code_hash(link.token_hash, code.strip())):
        # Conditional, like `use`: a code typed twice at once confirms once.
        spent = await session.scalar(
            update(PasswordLink)
            .where(PasswordLink.id == link.id, *_live())
            .values(used_at=func.now())
            .returning(PasswordLink.id)
        )
        return CodeResult.RIGHT if spent is not None else CodeResult.EXPIRED
    # One UPDATE that counts and, at the limit, uses it up: wrong codes typed at
    # once all count.
    tries = await session.scalar(
        update(PasswordLink)
        .where(PasswordLink.id == link.id, *_live())
        .values(
            tries=PasswordLink.tries + 1,
            used_at=case((PasswordLink.tries + 1 >= CODE_TRIES, func.now()), else_=None),
        )
        .returning(PasswordLink.tries)
    )
    return CodeResult.WRONG if tries is not None and tries < CODE_TRIES else CodeResult.EXPIRED
