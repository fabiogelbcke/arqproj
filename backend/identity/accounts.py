"""Creating and finding staff accounts.

Runtime code shared by everything that creates accounts: the `staff` command now,
a sign-up page or invitations later. Every function works within the tenant the
session is scoped to (`scope_to_tenant`); other tenants' accounts are invisible.
"""

from __future__ import annotations

from sqlalchemy import func, null, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.identity.emails import tidy_email
from backend.identity.models import LoginSession, Role, User
from backend.identity.passwords import hash_password

MIN_PASSWORD_LENGTH = 8
# One change to an account's email confirmation at a time: a code, a link, or a
# correction of the address must not interleave (a link confirming the old address
# while a correction writes the new one).
_LOCK_CONFIRMATION = text("SELECT pg_advisory_xact_lock(hashtext('email-code'), hashtext(:user))")


class AccountError(ValueError):
    """Bad input for an account (shown to whoever is creating it)."""


class PasswordTooShort(AccountError):
    def __init__(self) -> None:
        super().__init__(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")


def normalize_email(email: str) -> str:
    return tidy_email(email)


def _check_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordTooShort


async def find_user(session: AsyncSession, email: str) -> User | None:
    # Filtered by tenant explicitly too: owner-run commands may connect as a login
    # that row-level security does not bind (a superuser locally).
    return await session.scalar(
        select(User).where(
            User.tenant_id == func.current_tenant_id(), User.email == normalize_email(email)
        )
    )


async def create_user(
    session: AsyncSession,
    *,
    email: str,
    name: str,
    role: Role = Role.MEMBER,
    password: str | None = None,
    password_hash: str | None = None,
    email_confirmed: bool = True,
) -> User:
    """Without a password, the person chooses one through an invite link (`links`).
    `password_hash` is one from `new_password_hash`, made before the transaction.
    Unconfirmed (the shared link, A36): it signs in only to confirm the email."""
    if role not in set(Role):
        raise AccountError(f"Role must be one of: {', '.join(Role)}")
    if password is not None:
        password_hash = await new_password_hash(password)
    if await find_user(session, email) is not None:
        raise AccountError(f"There is already an account for {normalize_email(email)}")
    user = User(
        email=normalize_email(email),
        name=name.strip(),
        role=Role(role),
        password_hash=password_hash,
    )
    if not email_confirmed:
        # SQL's NULL: a plain None would leave the column to its default (now).
        user.email_confirmed_at = null()
    session.add(user)
    await session.flush()
    if not email_confirmed:
        await session.refresh(user, ["email_confirmed_at"])
    return user


async def new_password_hash(password: str) -> str:
    """Check a chosen password and hash it. Slow on purpose: call it before opening
    a transaction, so no database connection waits on it."""
    _check_password(password)
    return await hash_password(password)


async def lock_confirmation(session: AsyncSession, user_id) -> None:
    """Hold the account's confirmation lock until the transaction ends."""
    await session.execute(_LOCK_CONFIRMATION, {"user": str(user_id)})


async def confirm_email(session: AsyncSession, user: User) -> None:
    """The address is shown to be theirs (a code, a confirmation, an invite or a
    reset link): the account works fully."""
    if user.email_confirmed_at is None:
        user.email_confirmed_at = func.now()
        await session.flush()
        await session.refresh(user, ["email_confirmed_at"])


async def set_password(session: AsyncSession, user: User, password_hash: str) -> None:
    """Store a hash from `new_password_hash`."""
    user.password_hash = password_hash
    # A new password ends every existing sign-in (e.g. after a stolen cookie).
    await session.execute(
        update(LoginSession)
        .where(LoginSession.user_id == user.id, LoginSession.revoked_at.is_(None))
        .values(revoked_at=func.now())
    )
    await session.flush()
