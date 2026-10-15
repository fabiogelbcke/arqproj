"""Staff sign-in for the painel: the session API and the `current_staff` dependency.

    POST   /api/session   sign in with email and password
    DELETE /api/session   sign out (needs the CSRF token)
    GET    /api/me        who is signed in, or 401

The cookie holds only a random token (see `backend.identity.sessions`). Every
state-changing staff request must also send the session's CSRF token in the
`X-CSRF-Token` header (`require_csrf`).
"""

from __future__ import annotations

import hmac
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import anyio
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.engine import get_tenant_session
from backend.identity import accounts, sessions
from backend.identity.models import LoginSession, Role
from backend.identity.passwords import verify_password
from backend.tenancy.models import Locale
from backend.tenancy.resolve import CurrentTenant, current_tenant
from backend.web.errors import ApiError, ErrorCode, documented

COOKIE = "portal_session"
CSRF_HEADER = "X-CSRF-Token"
# Added to every failed sign-in, to slow down password guessing.
FAILED_LOGIN_DELAY = 1.0

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


class MeOut(BaseModel):
    email: str
    name: str
    role: Role
    tenant_slug: str
    tenant_name: str
    # The language the screens show their own text in.
    tenant_locale: Locale
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


async def require_csrf(
    request: Request, staff: CurrentStaff = Depends(current_staff)
) -> CurrentStaff:
    """For state-changing requests: the session's CSRF token must come back."""
    sent = request.headers.get(CSRF_HEADER, "")
    if not hmac.compare_digest(sent, staff.csrf_token):
        raise ApiError(403, ErrorCode.CSRF_TOKEN_MISSING_OR_WRONG)
    return staff


def _me(staff_email: str, name: str, role: Role, tenant: CurrentTenant, csrf: str) -> MeOut:
    return MeOut(
        email=staff_email,
        name=name,
        role=role,
        tenant_slug=tenant.slug,
        tenant_name=tenant.name,
        tenant_locale=tenant.locale,
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
    return _me(user.email, user.name, user.role, tenant, row.csrf_token)


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


@router.get("/me", responses=documented(401))
async def me(
    staff: CurrentStaff = Depends(current_staff),
    tenant: CurrentTenant = Depends(current_tenant),
) -> MeOut:
    return _me(staff.email, staff.name, staff.role, tenant, staff.csrf_token)
