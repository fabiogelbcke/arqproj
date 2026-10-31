"""A staff member's own account ("Minha conta"): their name, password and email.

    PATCH /api/me              change your name (as the team and clients see it)
    POST  /api/me/password     change your password: the current one first
    POST  /api/me/email/change change your email: the current password first

Changing the password ends every sign-in of the account, this one included
(accounts.set_password), then signs this device in again, so a stolen cookie
stops working at once. Wrong current passwords are limited like a page's: five
in 15 minutes, then 15 minutes' wait (backend/web/attempts.py), per account.
Changing the email (with the current password, the same limit) makes the new
address the account's, unconfirmed: a code goes to it, and the painel asks for it
as at signup (backend/web/email_confirmation.py) before anything else works. It
also ends the account's other sign-ins. The old address gets a notice, so an
unexpected change gets noticed.
"""

from __future__ import annotations

import anyio
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.engine import get_tenant_session
from backend.identity import accounts
from backend.identity.emails import is_email, tidy_email
from backend.identity.models import LoginSession, User
from backend.identity.passwords import verify_password
from backend.notifications.office import office_of
from backend.notifications.password_reset import email_changed_email
from backend.tenancy.resolve import CurrentTenant, current_tenant
from backend.web import attempts
from backend.web.auth import FAILED_LOGIN_DELAY, CurrentStaff, MeOut, require_csrf, signed_in
from backend.web.email_confirmation import _LOCK_EMAIL, _me_now, new_code, send
from backend.web.errors import ApiError, ErrorCode, documented
from backend.web.team import _name

router = APIRouter(prefix="/api")


async def own_account(staff: CurrentStaff = Depends(require_csrf)) -> CurrentStaff:
    """The signed-in person changing their own account: never Suporte Unio (A43),
    whose details belong to no one."""
    if staff.support_until is not None:
        raise ApiError(403, ErrorCode.SUPPORT_ACCOUNT)
    return staff


class NameIn(BaseModel):
    name: str = Field(max_length=200)


@router.patch("/me", status_code=204, responses=documented(401, 403, 422))
async def rename_me(
    body: NameIn,
    staff: CurrentStaff = Depends(own_account),
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
    staff: CurrentStaff = Depends(own_account),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> MeOut:
    try:
        # Before anything else: a too-short password costs no try.
        password_hash = await accounts.new_password_hash(body.password)
    except accounts.PasswordTooShort:
        raise ApiError(422, ErrorCode.PASSWORD_TOO_SHORT) from None
    user = await _check_current(staff, db, body.current)
    await accounts.set_password(db, user, password_hash)  # ends every sign-in
    result = await signed_in(request, response, tenant, db, user)  # this device again
    posthog_client = getattr(request.app.state, "posthog", None)
    if posthog_client is not None:
        posthog_client.capture("password_set")  # A39, as a reset link's
    return result


class EmailChangeIn(BaseModel):
    current: str = Field(max_length=200)
    email: str = Field(max_length=500)


async def _check_current(
    staff: CurrentStaff, db: AsyncSession, current: str, *, confirmation: bool = False
) -> User:
    """The account, locked for this transaction, once its current password is
    checked (within the per-account limit). The check runs with no connection held
    and no lock (it's slow); so afterwards the row is read again under its lock, and
    if the password changed meanwhile (another tab, a reset), this request loses:
    a change checked against an outdated password never overwrites a newer one.
    `confirmation`: the account's confirmation lock first, in the order the code
    flow takes them (backend/web/email_confirmation.py), so the two never deadlock."""
    key = _limit_key(staff)
    if not attempts.admit(*key):
        raise ApiError(429, ErrorCode.TOO_MANY_ATTEMPTS)
    user = await db.get(User, staff.user_id)
    checked = user.password_hash if user else None
    await db.commit()  # the connection back before the slow check
    if user is None or not await verify_password(checked, current):
        attempts.failed(*key)
        await anyio.sleep(FAILED_LOGIN_DELAY)
        raise ApiError(422, ErrorCode.CURRENT_PASSWORD_WRONG)
    attempts.succeeded(*key)
    if confirmation:
        await accounts.lock_confirmation(db, staff.user_id)
    user = await db.get(User, staff.user_id, with_for_update=True, populate_existing=True)
    if user is None or user.password_hash != checked:
        raise ApiError(422, ErrorCode.CURRENT_PASSWORD_WRONG)  # changed meanwhile
    return user


@router.post("/me/email/change", responses=documented(401, 403, 409, 422, 429, 503))
async def change_email(
    body: EmailChangeIn,
    request: Request,
    staff: CurrentStaff = Depends(own_account),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> MeOut:
    email = tidy_email(body.email)
    if not is_email(email):
        raise ApiError(422, ErrorCode.INVALID_EMAIL)
    user = await _check_current(staff, db, body.current, confirmation=True)
    if email == user.email:
        raise ApiError(422, ErrorCode.EMAIL_UNCHANGED)
    await db.execute(_LOCK_EMAIL, {"email": email})
    if await accounts.find_user(db, email) is not None:
        raise ApiError(409, ErrorCode.ACCOUNT_EXISTS)
    old = user.email
    user.email = email
    user.email_confirmed_at = None  # until the code from the new address is typed
    # Unconfirmed, any of the account's sessions may correct the address with no
    # password (email_confirmation.correct_email): so only this device stays signed
    # in, and a cookie stolen elsewhere can't redirect the code (Codex, PR #157).
    await db.execute(
        update(LoginSession)
        .where(
            LoginSession.user_id == user.id,
            LoginSession.id != staff.session_id,
            LoginSession.revoked_at.is_(None),
        )
        .values(revoked_at=func.now())
    )
    await db.flush()
    message = await new_code(db, request, tenant, user)
    office = await office_of(db, request.app.state.settings, tenant.id)
    await db.commit()
    # The notice first: whatever happens to the code, the old address hears of it.
    notice = email_changed_email(office, user.name, old, email, message.idempotency_key)
    await send(request, tenant, notice, "/api/me/email/change")
    if not await send(request, tenant, message, "/api/me/email/change"):
        raise ApiError(503, ErrorCode.EMAIL_NOT_SENT)  # "Reenviar código" on the next screen
    return await _me_now(db, tenant, staff, user)
