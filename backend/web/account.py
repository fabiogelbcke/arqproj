"""A staff member's own account ("Minha conta"): their name and their password.

    PATCH /api/me            change your name (as the team and clients see it)
    POST  /api/me/password   change your password: the current one first

Changing the password ends every sign-in of the account, this one included
(accounts.set_password), then signs this device in again, so a stolen cookie
stops working at once. Wrong current passwords are limited like a page's: five
in 15 minutes, then 15 minutes' wait (backend/web/attempts.py), per account.
Changing the email is later: it needs the new address confirmed first.
"""

from __future__ import annotations

import anyio
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.engine import get_tenant_session
from backend.identity import accounts
from backend.identity.models import User
from backend.identity.passwords import verify_password
from backend.tenancy.resolve import CurrentTenant, current_tenant
from backend.web import attempts
from backend.web.auth import FAILED_LOGIN_DELAY, CurrentStaff, MeOut, require_csrf, signed_in
from backend.web.errors import ApiError, ErrorCode, documented
from backend.web.team import _name

router = APIRouter(prefix="/api")


class NameIn(BaseModel):
    name: str = Field(max_length=200)


@router.patch("/me", status_code=204, responses=documented(401, 403, 422))
async def rename_me(
    body: NameIn,
    staff: CurrentStaff = Depends(require_csrf),
    db: AsyncSession = Depends(get_tenant_session),
) -> None:
    await db.execute(update(User).where(User.id == staff.user_id).values(name=_name(body.name)))
    await db.commit()


class PasswordChangeIn(BaseModel):
    current: str = Field(max_length=200)
    password: str = Field(max_length=200)


def _limit_key(staff: CurrentStaff) -> tuple[str, str]:
    return (f"account:{staff.user_id}", "password")


@router.post("/me/password", responses=documented(401, 403, 422, 429))
async def change_password(
    body: PasswordChangeIn,
    request: Request,
    response: Response,
    staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> MeOut:
    try:
        # Before anything else: a too-short password costs no try.
        password_hash = await accounts.new_password_hash(body.password)
    except accounts.PasswordTooShort:
        raise ApiError(422, ErrorCode.PASSWORD_TOO_SHORT) from None
    key = _limit_key(staff)
    if not attempts.admit(*key):
        raise ApiError(429, ErrorCode.TOO_MANY_ATTEMPTS)
    user = await db.get(User, staff.user_id)
    # Hand the connection back before the slow check, as signing in does.
    await db.commit()
    if user is None or not await verify_password(user.password_hash, body.current):
        attempts.failed(*key)
        await anyio.sleep(FAILED_LOGIN_DELAY)
        raise ApiError(422, ErrorCode.CURRENT_PASSWORD_WRONG)
    attempts.succeeded(*key)
    user = await db.get(User, staff.user_id)
    await accounts.set_password(db, user, password_hash)  # ends every sign-in
    return await signed_in(request, response, tenant, db, user)  # this device again
