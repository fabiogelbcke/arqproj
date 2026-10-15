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

import anyio
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.engine import get_tenant_session
from backend.identity import accounts, sessions
from backend.identity.models import LoginSession
from backend.identity.passwords import verify_password
from backend.tenancy.resolve import CurrentTenant, current_tenant

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
    role: str
    session_id: uuid.UUID
    csrf_token: str


class LoginIn(BaseModel):
    email: str
    password: str


class MeOut(BaseModel):
    email: str
    name: str
    role: str
    tenant_slug: str
    tenant_name: str
    csrf_token: str


def _not_signed_in() -> HTTPException:
    return HTTPException(401, detail={"error": "not_signed_in"})


async def current_staff(
    request: Request, db: AsyncSession = Depends(get_tenant_session)
) -> CurrentStaff:
    """The signed-in staff member of this tenant, or 401."""
    token = request.cookies.get(COOKIE)
    found = await sessions.find_active(db, token) if token else None
    if found is None:
        raise _not_signed_in()
    row, user = found
    await db.commit()  # keeps an extended expiry, if find_active extended it
    return CurrentStaff(user.id, user.email, user.name, user.role, row.id, row.csrf_token)


async def require_csrf(
    request: Request, staff: CurrentStaff = Depends(current_staff)
) -> CurrentStaff:
    """For state-changing requests: the session's CSRF token must come back."""
    sent = request.headers.get(CSRF_HEADER, "")
    if not hmac.compare_digest(sent, staff.csrf_token):
        raise HTTPException(403, detail={"error": "csrf_token_missing_or_wrong"})
    return staff


def _me(staff_email: str, name: str, role: str, tenant: CurrentTenant, csrf: str) -> MeOut:
    return MeOut(
        email=staff_email,
        name=name,
        role=role,
        tenant_slug=tenant.slug,
        tenant_name=tenant.name,
        csrf_token=csrf,
    )


@router.post("/session")
async def sign_in(
    body: LoginIn,
    request: Request,
    response: Response,
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> MeOut:
    user = await accounts.find_user(db, body.email)
    # Same work and the same answer whether the email or the password is wrong.
    if not await verify_password(user.password_hash if user else None, body.password):
        await anyio.sleep(FAILED_LOGIN_DELAY)
        raise HTTPException(
            401,
            detail={"error": "invalid_credentials", "message": "E-mail ou senha incorretos."},
        )
    token, row = await sessions.start(db, user)
    await db.commit()
    response.set_cookie(
        COOKIE,
        token,
        max_age=int(sessions.LIFETIME.total_seconds()),
        path="/",
        httponly=True,
        samesite="lax",
        secure=request.app.state.settings.deployed,
    )
    return _me(user.email, user.name, user.role, tenant, row.csrf_token)


@router.delete("/session", status_code=204)
async def sign_out(
    response: Response,
    staff: CurrentStaff = Depends(require_csrf),
    db: AsyncSession = Depends(get_tenant_session),
) -> None:
    row = await db.get(LoginSession, staff.session_id)
    await sessions.revoke(db, row)
    await db.commit()
    response.delete_cookie(COOKIE, path="/")


@router.get("/me")
async def me(
    staff: CurrentStaff = Depends(current_staff),
    tenant: CurrentTenant = Depends(current_tenant),
) -> MeOut:
    return _me(staff.email, staff.name, staff.role, tenant, staff.csrf_token)
