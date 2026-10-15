"""Creating and finding staff accounts.

Runtime code shared by everything that creates accounts: the `staff` command now,
a sign-up page or invitations later. Every function works within the tenant the
session is scoped to (`scope_to_tenant`); other tenants' accounts are invisible.
"""

from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.identity.models import LoginSession, Role, User
from backend.identity.passwords import hash_password

MIN_PASSWORD_LENGTH = 8


class AccountError(ValueError):
    """Bad input for an account (shown to whoever is creating it)."""


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _check_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AccountError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")


async def find_user(session: AsyncSession, email: str) -> User | None:
    # Filtered by tenant explicitly too: owner-run commands may connect as a login
    # that row-level security does not bind (a superuser locally).
    return await session.scalar(
        select(User).where(
            User.tenant_id == func.current_tenant_id(), User.email == normalize_email(email)
        )
    )


async def create_user(
    session: AsyncSession, *, email: str, name: str, password: str, role: Role = Role.MEMBER
) -> User:
    if role not in set(Role):
        raise AccountError(f"Role must be one of: {', '.join(Role)}")
    _check_password(password)
    if await find_user(session, email) is not None:
        raise AccountError(f"There is already an account for {normalize_email(email)}")
    user = User(
        email=normalize_email(email),
        name=name.strip(),
        role=Role(role),
        password_hash=hash_password(password),
    )
    session.add(user)
    await session.flush()
    return user


async def set_password(session: AsyncSession, email: str, password: str) -> User:
    user = await find_user(session, email)
    if user is None:
        raise AccountError(f"No account for {normalize_email(email)}")
    _check_password(password)
    user.password_hash = hash_password(password)
    # A new password ends every existing sign-in (e.g. after a stolen cookie).
    await session.execute(
        update(LoginSession)
        .where(LoginSession.user_id == user.id, LoginSession.revoked_at.is_(None))
        .values(revoked_at=func.now())
    )
    await session.flush()
    return user
