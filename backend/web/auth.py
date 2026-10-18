"""Staff sign-in for the painel: the session API and the `current_staff` dependency.

    POST   /api/session         sign in with email and password
    DELETE /api/session         sign out (needs the CSRF token)
    GET    /api/me              who is signed in, or 401
    POST   /api/password-link   whose invite/reset link is this (before the form)
    POST   /api/password        choose a password with a link, then signed in
    POST   /api/password-reset  "Esqueceu a senha?": email a link, if the account exists

The cookie holds only a random token (see `backend.identity.sessions`). Every
state-changing staff request must also send the session's CSRF token in the
`X-CSRF-Token` header (`require_csrf`).
"""

from __future__ import annotations

import hmac
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import anyio
from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.engine import get_tenant_session
from backend.identity import accounts, links, sessions
from backend.identity.models import LinkKind, LoginSession, Role
from backend.identity.passwords import verify_password
from backend.notifications.email import Email, EmailError, sender_for
from backend.notifications.office import office_of
from backend.notifications.password_reset import reset_email
from backend.office.profile import display_name
from backend.tenancy.models import Locale
from backend.tenancy.resolve import CurrentTenant, current_tenant
from backend.web import attempts
from backend.web.errors import ApiError, ErrorCode, documented

COOKIE = "portal_session"
CSRF_HEADER = "X-CSRF-Token"
# Added to every failed sign-in, to slow down password guessing.
FAILED_LOGIN_DELAY = 1.0

# "Esqueceu a senha?": at most one email to an address every few minutes, and a
# few requests from one device in 15 minutes (counted as the client pages' tries).
RESET_EVERY = timedelta(minutes=2)
RESET_TRIES = "password-reset"
_LOCK_RESET = text("SELECT pg_advisory_xact_lock(hashtext('password-reset'), hashtext(:user))")

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


@dataclass(frozen=True)
class CurrentStaff:
    user_id: uuid.UUID
    email: str
    name: str
    role: Role
    session_id: uuid.UUID
    csrf_token: str


class LoginIn(BaseModel):
    email: str
    password: str


class LinkIn(BaseModel):
    token: str


class ResetIn(BaseModel):
    email: str


class LinkOut(BaseModel):
    email: str
    name: str
    kind: LinkKind


class ChoosePasswordIn(BaseModel):
    token: str
    password: str


class MeOut(BaseModel):
    email: str
    name: str
    role: Role
    tenant_slug: str
    tenant_name: str
    # The language the screens show their own text in.
    tenant_locale: Locale
    # Times are shown in the office's zone, wherever the viewer is.
    tenant_timezone: str
    csrf_token: str


def _not_signed_in() -> ApiError:
    return ApiError(401, ErrorCode.NOT_SIGNED_IN)


def _set_cookie(request: Request, response: Response, token: str, expires_at: datetime) -> None:
    response.set_cookie(
        COOKIE,
        token,
        max_age=max(0, int((expires_at - datetime.now(UTC)).total_seconds())),
        path="/",
        httponly=True,
        samesite="lax",
        secure=request.app.state.settings.deployed,
    )


async def current_staff(
    request: Request, response: Response, db: AsyncSession = Depends(get_tenant_session)
) -> CurrentStaff:
    """The signed-in staff member of this tenant, or 401."""
    token = request.cookies.get(COOKIE)
    found = await sessions.find_active(db, token) if token else None
    if found is None:
        raise _not_signed_in()
    row, user = found
    await db.commit()  # keeps an extended expiry, if find_active extended it
    # The browser keeps the cookie as long as the session lives, so an active
    # person is not signed out 30 days after signing in.
    _set_cookie(request, response, token, row.expires_at)
    return CurrentStaff(user.id, user.email, user.name, user.role, row.id, row.csrf_token)


async def optional_staff(
    request: Request, response: Response, db: AsyncSession = Depends(get_tenant_session)
) -> CurrentStaff | None:
    """The signed-in staff member, or None for anyone else (public pages)."""
    if not request.cookies.get(COOKIE):
        return None
    try:
        return await current_staff(request, response, db)
    except ApiError:
        return None


async def require_csrf(
    request: Request, staff: CurrentStaff = Depends(current_staff)
) -> CurrentStaff:
    """For state-changing requests: the session's CSRF token must come back."""
    sent = request.headers.get(CSRF_HEADER, "")
    if not hmac.compare_digest(sent, staff.csrf_token):
        raise ApiError(403, ErrorCode.CSRF_TOKEN_MISSING_OR_WRONG)
    return staff


def _me(
    staff_email: str, name: str, role: Role, tenant: CurrentTenant, office: str, csrf: str
) -> MeOut:
    return MeOut(
        email=staff_email,
        name=name,
        role=role,
        tenant_slug=tenant.slug,
        tenant_name=office,
        tenant_locale=tenant.locale,
        tenant_timezone=tenant.timezone,
        csrf_token=csrf,
    )


@router.post("/session", responses=documented(401, 422))
async def sign_in(
    body: LoginIn,
    request: Request,
    response: Response,
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> MeOut:
    user = await accounts.find_user(db, body.email)
    # Hand the database connection back before the slow part (a queued password
    # check, then the delay), so failed attempts cannot hold the whole pool.
    await db.commit()
    # Same work and the same answer whether the email or the password is wrong.
    if not await verify_password(user.password_hash if user else None, body.password):
        await anyio.sleep(FAILED_LOGIN_DELAY)
        raise ApiError(401, ErrorCode.INVALID_CREDENTIALS)
    token, row = await sessions.start(db, user)
    await db.commit()
    _set_cookie(request, response, token, row.expires_at)
    return _me(
        user.email, user.name, user.role, tenant, await display_name(db, tenant), row.csrf_token
    )


@router.delete("/session", status_code=204, responses=documented(401, 403))
async def sign_out(
    response: Response,
    staff: CurrentStaff = Depends(require_csrf),
    db: AsyncSession = Depends(get_tenant_session),
) -> None:
    row = await db.get(LoginSession, staff.session_id)
    await sessions.revoke(db, row)
    await db.commit()
    del response.headers["set-cookie"]  # current_staff's refresh of the same cookie
    response.delete_cookie(COOKIE, path="/")


@router.post("/password-link", responses=documented(404, 422))
async def check_password_link(
    body: LinkIn, db: AsyncSession = Depends(get_tenant_session)
) -> LinkOut:
    """Before showing the "choose your password" form: whose link is it, and does
    it still work?"""
    found = await links.find(db, body.token)
    if found is None:
        raise ApiError(404, ErrorCode.LINK_INVALID)
    link, user = found
    return LinkOut(email=user.email, name=user.name, kind=link.kind)


@router.post("/password", responses=documented(404, 422))
async def choose_password(
    body: ChoosePasswordIn,
    request: Request,
    response: Response,
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> MeOut:
    """Use an invite or reset link: set the password, end other sessions, sign in."""
    try:
        # Before touching the database, so no connection waits on the hashing; a
        # too-short password leaves the link usable.
        password_hash = await accounts.new_password_hash(body.password)
    except accounts.PasswordTooShort:
        raise ApiError(422, ErrorCode.PASSWORD_TOO_SHORT) from None
    user = await links.use(db, body.token)
    if user is None:
        raise ApiError(404, ErrorCode.LINK_INVALID)
    await accounts.set_password(db, user, password_hash)
    token, row = await sessions.start(db, user)
    await db.commit()
    _set_cookie(request, response, token, row.expires_at)
    return _me(
        user.email, user.name, user.role, tenant, await display_name(db, tenant), row.csrf_token
    )


@router.get("/me", responses=documented(401))
async def me(
    staff: CurrentStaff = Depends(current_staff),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> MeOut:
    office = await display_name(db, tenant)
    return _me(staff.email, staff.name, staff.role, tenant, office, staff.csrf_token)


@router.post("/password-reset", status_code=204, responses=documented(422, 429))
async def ask_password_reset(
    body: ResetIn,
    request: Request,
    background: BackgroundTasks,
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> None:
    """Emails a link to choose a new password to this office's account with that
    address. The same answer, as fast, whether or not there is one: the email
    goes after the response, so neither can tell who has an account."""
    who = attempts.device(request)
    if not attempts.admit(RESET_TRIES, who):
        raise ApiError(429, ErrorCode.TOO_MANY_ATTEMPTS)
    attempts.failed(RESET_TRIES, who)  # every request counts toward the limit
    user = await accounts.find_user(db, body.email)
    if user is None:
        return
    # One request per account at a time, until this transaction ends: two at once
    # must not both find no recent link and both send.
    await db.execute(_LOCK_RESET, {"user": str(user.id)})
    if await links.made_since(db, user, LinkKind.RESET, datetime.now(UTC) - RESET_EVERY):
        return
    token = await links.create(db, user, LinkKind.RESET)
    office = await office_of(db, request.app.state.settings, tenant.id)
    await db.commit()
    background.add_task(_send, request, tenant, reset_email(office, user.name, user.email, token))


async def _send(request: Request, tenant: CurrentTenant, email: Email) -> None:
    try:
        http = getattr(request.app.state, "http", None)  # set up at app start
        await sender_for(request.app.state.settings, http).send(email)
    except EmailError as error:
        # The person sees no error (nothing may say whether the account exists):
        # they can ask again; the log has why.
        log.error(
            "password reset email failed: route=/api/password-reset tenant=%s %s",
            tenant.slug,
            error.detail,
        )
