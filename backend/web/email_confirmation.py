"""Confirming the email of someone who joined through the office's shared link (A36,
revised 25 Oct 2026). They chose a password when joining and are signed in, but
the account does nothing else until a code emailed to the address is typed in, or
the email's link is opened.

    POST   /api/me/email-code          the code, typed where they signed up
    POST   /api/me/email-code/resend   a new code (and link) to their address
    PUT    /api/me/email               a mistyped address corrected, and a new code
    POST   /api/email-confirmation     the email's link, opened anywhere

The code works only in the account's own session, so signing up with someone
else's address gets nowhere: the code goes to them. Wrong codes count per account
(5 in 15 minutes, as passwords on client pages), and per code (`links.CODE_TRIES`).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.engine import get_tenant_session
from backend.identity import accounts, links
from backend.identity.emails import is_email, tidy_email
from backend.identity.models import LinkKind, User
from backend.notifications.email import Email, EmailError, sender_for
from backend.notifications.office import office_of
from backend.notifications.password_reset import confirm_email
from backend.office.profile import display_name
from backend.tenancy.resolve import CurrentTenant, current_tenant
from backend.web import attempts
from backend.web.auth import CurrentStaff, MeOut, me_out, require_csrf_account
from backend.web.errors import ApiError, ErrorCode, documented

RESEND_EVERY = timedelta(minutes=2)  # at most one code to an account in this time
CODE_TRIES = "email-code"
# Corrections to a new address send at once (the typo is usually noticed right
# away), so they count instead: 5 per account in 15 minutes, as wrong codes.
CORRECTIONS = "email-correction"
# One change to an account's confirmation at a time (a double click on "Reenviar
# código" must not send two).
_LOCK = text("SELECT pg_advisory_xact_lock(hashtext('email-code'), hashtext(:user))")
_LOCK_EMAIL = text("SELECT pg_advisory_xact_lock(hashtext('staff-email'), hashtext(:email))")

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


class CodeIn(BaseModel):
    code: str = Field(max_length=20)


class EmailIn(BaseModel):
    email: str = Field(max_length=500)


class TokenIn(BaseModel):
    token: str = Field(max_length=200)


async def new_code(db: AsyncSession, request: Request, tenant: CurrentTenant, user: User) -> Email:
    """A new code and link for `user` (any earlier one stops working), as its email.
    On the office's stored address, never one taken from the request (section 4)."""
    token, code = await links.create_confirmation(db, user)
    office = await office_of(db, request.app.state.settings, tenant.id)
    return confirm_email(office, user.name, user.email, token, code)


async def send(request: Request, tenant: CurrentTenant, email: Email, route: str) -> bool:
    """Whether it went; a failure is logged with its detail, and the person is told
    only that the email couldn't go (AGENTS.md)."""
    try:
        http = getattr(request.app.state, "http", None)  # set up at app start
        await sender_for(request.app.state.settings, http).send(email)
        return True
    except EmailError as error:
        log.error(
            "confirmation email failed: route=%s tenant=%s %s", route, tenant.slug, error.detail
        )
        return False


async def _unconfirmed(db: AsyncSession, account: CurrentStaff) -> User:
    """The signed-in account, still unconfirmed, read again under its lock."""
    await db.execute(_LOCK, {"user": str(account.user_id)})
    user = await db.get(User, account.user_id, populate_existing=True)
    if user is None or user.email_confirmed_at is not None:
        raise ApiError(409, ErrorCode.ALREADY_CONFIRMED)
    return user


async def _me_now(
    db: AsyncSession, tenant: CurrentTenant, account: CurrentStaff, user: User
) -> MeOut:
    return me_out(
        user.email,
        user.name,
        user.role,
        tenant,
        await display_name(db, tenant),
        account.csrf_token,
        user.tour_seen_at is not None,
        user.email_confirmed_at is not None,
    )


@router.post("/me/email-code", responses=documented(401, 403, 409, 410, 422, 429))
async def enter_code(
    body: CodeIn,
    account: CurrentStaff = Depends(require_csrf_account),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> MeOut:
    """The code from the email: right, and the account works fully."""
    who = str(account.user_id)
    if not attempts.admit(CODE_TRIES, who):
        raise ApiError(429, ErrorCode.TOO_MANY_ATTEMPTS)
    try:
        user = await _unconfirmed(db, account)
        result = await links.use_code(db, user, body.code)
    except BaseException:
        attempts.succeeded(CODE_TRIES, who)  # not a wrong code: release the try
        raise
    if result is links.CodeResult.RIGHT:
        attempts.succeeded(CODE_TRIES, who)
        await accounts.confirm_email(db, user)
        await db.commit()
        log.info("staff %s confirmed their email in %s", user.id, tenant.slug)
        return await _me_now(db, tenant, account, user)
    attempts.failed(CODE_TRIES, who)
    await db.commit()  # the wrong try counts on the code too
    if result is links.CodeResult.WRONG:
        raise ApiError(422, ErrorCode.EMAIL_CODE_WRONG)
    raise ApiError(410, ErrorCode.EMAIL_CODE_EXPIRED)


@router.post(
    "/me/email-code/resend", status_code=204, responses=documented(401, 403, 409, 429, 503)
)
async def resend_code(
    request: Request,
    account: CurrentStaff = Depends(require_csrf_account),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> None:
    user = await _unconfirmed(db, account)
    if await links.made_since(db, user, LinkKind.CONFIRM, datetime.now(UTC) - RESEND_EVERY):
        raise ApiError(429, ErrorCode.EMAIL_CODE_RECENT)
    message = await new_code(db, request, tenant, user)
    await db.commit()
    if not await send(request, tenant, message, "/api/me/email-code/resend"):
        raise ApiError(503, ErrorCode.EMAIL_NOT_SENT)


@router.put("/me/email", responses=documented(401, 403, 409, 422, 429, 503))
async def correct_email(
    body: EmailIn,
    request: Request,
    account: CurrentStaff = Depends(require_csrf_account),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> MeOut:
    """A mistyped address, corrected before it's confirmed (only then: changing a
    confirmed address comes with account settings). A new code goes to it."""
    email = tidy_email(body.email)
    if not is_email(email):
        raise ApiError(422, ErrorCode.INVALID_EMAIL)
    user = await _unconfirmed(db, account)
    if email == user.email:
        # Nothing to correct: a new code, under the resend's own limit.
        if await links.made_since(db, user, LinkKind.CONFIRM, datetime.now(UTC) - RESEND_EVERY):
            raise ApiError(429, ErrorCode.EMAIL_CODE_RECENT)
    else:
        who = str(user.id)
        if not attempts.admit(CORRECTIONS, who):
            raise ApiError(429, ErrorCode.TOO_MANY_ATTEMPTS)
        attempts.failed(CORRECTIONS, who)  # every correction counts toward the limit
        await db.execute(_LOCK_EMAIL, {"email": email})
        if await accounts.find_user(db, email) is not None:
            raise ApiError(409, ErrorCode.ACCOUNT_EXISTS)
        user.email = email
        await db.flush()
    message = await new_code(db, request, tenant, user)
    await db.commit()
    if not await send(request, tenant, message, "/api/me/email"):
        raise ApiError(503, ErrorCode.EMAIL_NOT_SENT)
    return await _me_now(db, tenant, account, user)


@router.post("/email-confirmation", status_code=204, responses=documented(404, 422))
async def confirm_by_link(
    body: TokenIn,
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> None:
    """The email's link: confirms the address wherever it's opened (often a phone,
    signed in or not); the person then signs in, or carries on where they were."""
    found = await links.find(db, body.token, (LinkKind.CONFIRM,))
    if found is None:
        raise ApiError(404, ErrorCode.LINK_INVALID)
    # Under the account's lock, as corrections and codes: an address corrected
    # meanwhile has retired this link, so `use` finds nothing to confirm.
    await db.execute(_LOCK, {"user": str(found[1].id)})
    user = await links.use(db, body.token, (LinkKind.CONFIRM,))
    if user is None:
        raise ApiError(404, ErrorCode.LINK_INVALID)
    await db.refresh(user)  # its address as it is now, after the lock
    await accounts.confirm_email(db, user)
    await db.commit()
    log.info("staff %s confirmed their email by link in %s", user.id, tenant.slug)
