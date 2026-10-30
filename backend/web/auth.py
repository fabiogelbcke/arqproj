"""Staff sign-in for the painel: the session API and the `current_staff` dependency.

    POST   /api/session         sign in with email and password
    DELETE /api/session         sign out (needs the CSRF token)
    GET    /api/me              who is signed in, or 401
    POST   /api/me/tour-seen    the project page's tour won't start again for them
    POST   /api/password-link   whose invite/reset link is this (before the form)
    POST   /api/password        choose a password with a link, then signed in
    POST   /api/password-reset  "Esqueceu a senha?": email a link, if the account exists

The cookie holds only a random token (see `backend.identity.sessions`). Every
state-changing staff request must also send the session's CSRF token in the
`X-CSRF-Token` header (`require_csrf`).

Someone who joined through the office's shared link and hasn't confirmed their
email yet (A36) signs in like anyone, but `current_staff` refuses them: only
`current_account` routes (who they are, signing out, confirming the email) work.
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
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.analytics import capture
from backend.db.engine import get_tenant_session
from backend.identity import accounts, links, sessions, support
from backend.identity.models import LinkKind, LoginSession, Role, User
from backend.identity.passwords import verify_password
from backend.notifications.email import Email, EmailError, sender_for
from backend.notifications.office import office_of
from backend.notifications.password_reset import reset_email
from backend.office.profile import display_name
from backend.tenancy.models import Feature, Locale
from backend.tenancy.resolve import CurrentTenant, current_tenant
from backend.web import attempts
from backend.web.errors import ApiError, ErrorCode, documented

COOKIE = "portal_session"
# Tags a support session's analytics events, which are dropped (`app.drop_support`).
SUPPORT_TAG = "unio_support"
CSRF_HEADER = "X-CSRF-Token"
# Added to every failed sign-in, to slow down password guessing.
FAILED_LOGIN_DELAY = 1.0

# "Esqueceu a senha?": at most one email to an address every few minutes, and a
# few requests from one device in 15 minutes (counted as the client pages' tries).
RESET_EVERY = timedelta(minutes=2)
RESET_TRIES = "password-reset"
RESET_ANSWER_AT = 0.5  # seconds: every request answers this late, at the earliest
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
    email_confirmed: bool = True
    # When a support session (A43) ends; None for the office's own staff.
    support_until: datetime | None = None


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


class AnalyticsOut(BaseModel):
    """Product analytics for the browser (A39), given only to signed-in staff and
    only where the server has PostHog set, so one image serves staging and
    production with each one's own key. Visitors get their own, cookieless setup
    from `/api/tenant` (`web.tenant.VisitorAnalyticsOut`)."""

    token: str  # PostHog's project token: public by design, not a secret
    host: str
    user_id: uuid.UUID  # the person, as the server identifies them
    tenant_id: uuid.UUID  # the office: PostHog's `tenant` group


class MeOut(BaseModel):
    id: uuid.UUID  # the account: "Meus projetos" (A41)
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
    # The project page's guided tour, once per account (Fabio, 18 Oct 2026).
    page_tour_seen: bool
    # False: joined through the shared link, and must confirm the email before
    # anything else (A36).
    email_confirmed: bool
    # Switched on for the office from the operator dashboard (A40).
    features: list[Feature]
    analytics: AnalyticsOut | None = None
    # An operator signed in as Suporte Unio (A43): when the session ends.
    support_until: datetime | None = None


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


async def current_account(
    request: Request, response: Response, db: AsyncSession = Depends(get_tenant_session)
) -> CurrentStaff:
    """Whoever is signed in to this tenant, confirmed or not, or 401. Only for the
    routes an unconfirmed account needs; everything else uses `current_staff`."""
    token = request.cookies.get(COOKIE)
    found = await sessions.find_active(db, token) if token else None
    if found is None:
        raise _not_signed_in()
    row, user = found
    await db.commit()  # keeps an extended expiry, if find_active extended it
    posthog_client = getattr(request.app.state, "posthog", None)
    if posthog_client is not None and user.support:
        posthog_client.tag(SUPPORT_TAG, True)  # dropped before sending (A43)
    elif posthog_client is not None:  # this request's events are this person's
        posthog_client.identify_context(str(user.id))
        posthog_client.set_context_session(str(row.id))
    # The browser keeps the cookie as long as the session lives, so an active
    # person is not signed out 30 days after signing in.
    _set_cookie(request, response, token, row.expires_at)
    return CurrentStaff(
        user.id,
        user.email,
        user.name,
        user.role,
        row.id,
        row.csrf_token,
        user.email_confirmed_at is not None,
        row.expires_at if user.support else None,
    )


async def current_staff(
    request: Request, response: Response, db: AsyncSession = Depends(get_tenant_session)
) -> CurrentStaff:
    """The signed-in staff member of this tenant, or 401; 403 until their email
    is confirmed."""
    account = await current_account(request, response, db)
    if not account.email_confirmed:
        raise ApiError(403, ErrorCode.EMAIL_UNCONFIRMED)
    return account


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


def _check_csrf(request: Request, staff: CurrentStaff) -> CurrentStaff:
    sent = request.headers.get(CSRF_HEADER, "")
    if not hmac.compare_digest(sent, staff.csrf_token):
        raise ApiError(403, ErrorCode.CSRF_TOKEN_MISSING_OR_WRONG)
    return staff


async def require_csrf(
    request: Request, staff: CurrentStaff = Depends(current_staff)
) -> CurrentStaff:
    """For state-changing requests: the session's CSRF token must come back."""
    return _check_csrf(request, staff)


async def require_csrf_account(
    request: Request, account: CurrentStaff = Depends(current_account)
) -> CurrentStaff:
    """`require_csrf` for the routes an unconfirmed account may use."""
    return _check_csrf(request, account)


def analytics_for(
    request: Request, user_id: uuid.UUID, tenant: CurrentTenant
) -> AnalyticsOut | None:
    settings = request.app.state.settings
    if not (settings.posthog_project_token and settings.posthog_host):
        return None
    return AnalyticsOut(
        token=settings.posthog_project_token,
        host=settings.posthog_host,
        user_id=user_id,
        tenant_id=tenant.id,
    )


def me_out(
    user_id: uuid.UUID,
    staff_email: str,
    name: str,
    role: Role,
    tenant: CurrentTenant,
    office: str,
    csrf: str,
    tour_seen: bool,
    email_confirmed: bool = True,
) -> MeOut:
    return MeOut(
        id=user_id,
        email=staff_email,
        name=name,
        role=role,
        tenant_slug=tenant.slug,
        tenant_name=office,
        tenant_locale=tenant.locale,
        tenant_timezone=tenant.timezone,
        csrf_token=csrf,
        page_tour_seen=tour_seen,
        email_confirmed=email_confirmed,
        features=sorted(tenant.features),
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
    return await signed_in(request, response, tenant, db, user)


async def signed_in(
    request: Request,
    response: Response,
    tenant: CurrentTenant,
    db: AsyncSession,
    user: User,
    method: str = "password",
) -> MeOut:
    """Start a session for `user` (its cookie on `response`), and say who they are.
    `method` says how, for analytics: password, google, link (a password set from an
    email's link) or join."""
    token, row = await sessions.start(db, user)
    await db.commit()
    _set_cookie(request, response, token, row.expires_at)
    posthog_client = getattr(request.app.state, "posthog", None)
    if posthog_client is not None:
        # This request began anonymously; identify the active request context once
        # its authenticated account and server session exist.
        posthog_client.identify_context(str(user.id))
        posthog_client.set_context_session(str(row.id))
        # Only the id and role (Fabio, 26 Oct 2026): no email or name in PostHog.
        posthog_client.set(properties={"role": str(user.role)})
        posthog_client.group_identify(
            "tenant", str(tenant.id), properties={"slug": tenant.slug, "name": tenant.name}
        )
        posthog_client.capture("user_signed_in", properties={"method": method})
    out = me_out(
        user.id,
        user.email,
        user.name,
        user.role,
        tenant,
        await display_name(db, tenant),
        row.csrf_token,
        user.tour_seen_at is not None,
        user.email_confirmed_at is not None,
    )
    out.analytics = analytics_for(request, user.id, tenant)
    return out


@router.delete("/session", status_code=204, responses=documented(401, 403))
async def sign_out(
    request: Request,
    response: Response,
    staff: CurrentStaff = Depends(require_csrf_account),
    db: AsyncSession = Depends(get_tenant_session),
) -> None:
    row = await db.get(LoginSession, staff.session_id)
    await sessions.revoke(db, row)
    await db.commit()
    posthog_client = getattr(request.app.state, "posthog", None)
    if posthog_client is not None:
        posthog_client.capture("user_signed_out")
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
    found = await links.find(db, body.token)
    if found is None:
        raise ApiError(404, ErrorCode.LINK_INVALID)
    # It confirms the address too: not while an unconfirmed address is being
    # corrected (that retires this link; `use` then finds nothing).
    await accounts.lock_confirmation(db, found[1].id)
    user = await links.use(db, body.token)
    if user is None:
        raise ApiError(404, ErrorCode.LINK_INVALID)
    await db.refresh(user)  # its address as it is now, after the lock
    await accounts.set_password(db, user, password_hash)
    # The link came to their inbox: that proves the address too.
    await accounts.confirm_email(db, user)
    result = await signed_in(request, response, tenant, db, user, method="link")
    posthog_client = getattr(request.app.state, "posthog", None)
    if posthog_client is not None:
        posthog_client.capture("password_set")
    return result


@router.get("/me", responses=documented(401))
async def me(
    request: Request,
    staff: CurrentStaff = Depends(current_account),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> MeOut:
    office = await display_name(db, tenant)
    seen = await db.scalar(select(User.tour_seen_at).where(User.id == staff.user_id))
    out = me_out(
        staff.user_id,
        staff.email,
        staff.name,
        staff.role,
        tenant,
        office,
        staff.csrf_token,
        seen is not None,
        staff.email_confirmed,
    )
    out.support_until = staff.support_until
    if staff.support_until is None:  # a support session counts for nobody (A43)
        out.analytics = analytics_for(request, staff.user_id, tenant)
    return out


@router.post("/support-session", responses=documented(404))
async def support_session(
    body: LinkIn,
    request: Request,
    response: Response,
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> MeOut:
    """An operator's entry link (A43) spent: this browser is Suporte Unio for an
    hour. The operator dashboard audited the entry when it made the link."""
    user = await support.use(db, body.token)
    if user is None:
        raise ApiError(404, ErrorCode.LINK_INVALID)
    token, row = await sessions.start(db, user, support.LIFETIME)
    await db.commit()
    _set_cookie(request, response, token, row.expires_at)
    log.info("support: session started in tenant %s as %s", tenant.id, user.role)
    out = me_out(
        user.id,
        user.email,
        user.name,
        user.role,
        tenant,
        await display_name(db, tenant),
        row.csrf_token,
        tour_seen=True,  # the tour is for the office's people
    )
    out.support_until = row.expires_at
    return out


@router.post("/me/tour-seen", status_code=204, responses=documented(401, 403))
async def tour_seen(
    request: Request,
    staff: CurrentStaff = Depends(require_csrf),
    db: AsyncSession = Depends(get_tenant_session),
) -> None:
    """The project page's tour, finished or closed: not offered again to this account
    on any device ("Ver tour" in the staff bar replays it)."""
    await db.execute(
        update(User)
        .where(User.id == staff.user_id, User.tour_seen_at.is_(None))
        .values(tour_seen_at=func.now())
    )
    await db.commit()
    capture(request, "page_tour_seen")


@router.post("/password-reset", status_code=204, responses=documented(422, 429))
async def ask_password_reset(
    body: ResetIn,
    request: Request,
    background: BackgroundTasks,
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> None:
    """Emails a link to choose a new password to this office's account with that
    address. The same answer whether or not there is one, and no sooner: every
    request takes RESET_ANSWER_AT, and the email goes after the response, so
    neither the answer nor its timing tells who has an account."""
    who = attempts.device(request)
    if not attempts.admit(RESET_TRIES, who):
        raise ApiError(429, ErrorCode.TOO_MANY_ATTEMPTS)
    attempts.failed(RESET_TRIES, who)  # every request counts toward the limit
    started = anyio.current_time()
    email = await _reset_link(body.email, request, tenant, db)
    await db.commit()  # the connection goes back before the wait
    await anyio.sleep(max(0.0, RESET_ANSWER_AT - (anyio.current_time() - started)))
    if email is not None:
        background.add_task(_send, request, tenant, email)


async def _reset_link(
    address: str, request: Request, tenant: CurrentTenant, db: AsyncSession
) -> Email | None:
    """A new reset link for the account with this address, as its email; None
    without an account, or when one went in the last RESET_EVERY."""
    user = await accounts.find_user(db, address)
    if user is None:
        return None
    # The account's confirmation lock, as an email correction takes it, then the
    # account as it is now: a correction that committed meanwhile must not get a
    # link sent to the old address that would then confirm the new one (A36).
    await accounts.lock_confirmation(db, user.id)
    await db.refresh(user)
    if user.email != accounts.normalize_email(address):
        return None
    # One request per account at a time, until this transaction ends: two at once
    # must not both find no recent link and both send.
    await db.execute(_LOCK_RESET, {"user": str(user.id)})
    if await links.made_since(db, user, LinkKind.RESET, datetime.now(UTC) - RESET_EVERY):
        return None
    token = await links.create(db, user, LinkKind.RESET)
    office = await office_of(db, request.app.state.settings, tenant.id)
    return reset_email(office, user.name, user.email, token)


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
