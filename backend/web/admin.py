"""The operator dashboard (A38, plan section 21): Unio's own view of every office.

    GET  /admin, /admin/...           the dashboard's page (its own small app)
    GET  /api/admin/me                the operator signed in, or 401
    POST /api/admin/signin            start Google sign-in: returns Google's address
    GET  /api/auth/google/callback    Google returns here
    POST /api/admin/signout           sign out (needs the CSRF token)
    POST /api/admin/dev-session       local only: sign in as an allowlisted email
    GET  /api/admin/offices           every office: counts and health
    GET  /api/admin/offices/{slug}    one office, with its team

Only on Unio's own address (OPERATOR_HOST): anywhere else these answer 404, as if
they did not exist. Only Google accounts on the deployment's allowlist
(OPERATOR_EMAILS) get in, checked again on every request, so taking an email off
the list ends its access at once. An operator session is a signed cookie for that
host alone, separate from office staff sessions, and short lived. Lifecycle
actions use a separate restricted database login and commit an audit event with
each change.
"""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from backend.db.isolation import scope_to_tenant
from backend.identity.models import Role
from backend.operators import actions, offices
from backend.operators.google_signin import GoogleSignIn, SignInError, new_verifier
from backend.operators.statistics import FileStats, load_files
from backend.security import keys
from backend.storage.base import StorageError
from backend.storage.google_connect import ConnectError
from backend.storage.models import StorageConnection, StorageKind
from backend.tenancy.middleware import OPERATOR_PAGE
from backend.tenancy.models import Tenant, TenantDomain, TenantStatus
from backend.tenancy.resolve import current_tenant, normalize_host
from backend.web import attempts, google_signin, pages
from backend.web.auth import optional_staff
from backend.web.drive import writer_for
from backend.web.errors import ApiError, ErrorCode, documented
from backend.web.page_files import _storage
from backend.web.request_id import current_request_id

log = logging.getLogger(__name__)
router = APIRouter()

PAGE = OPERATOR_PAGE
CALLBACK = "/api/auth/google/callback"
COOKIE = "unio_operator"
FLOW_COOKIE = "unio_operator_signin"
SESSION_PURPOSE = "operator-session"
FLOW_PURPOSE = "operator-signin"
SESSION_TTL = 8 * 3600  # a working day; then Google again
FLOW_TTL = 600  # long enough to sign in at Google
CSRF_HEADER = "X-CSRF-Token"
# Plan section 4, as the painel's (backend/web/painel.py): only this site's files.
POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'sha256-38RhXrc7EdReTKsOm23ZPOCUgniTUUcjky8QOOrQx6o='",
        "img-src 'self' data:",
        "font-src 'self'",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
)


def _on_operator_host(request: Request) -> None:
    host = normalize_host(request.headers.get("host"))
    if host != request.app.state.settings.operator_host:
        raise ApiError(404, ErrorCode.PAGE_NOT_FOUND)


class OperatorOut(BaseModel):
    email: str
    csrf_token: str
    # For the support-ID lookup and an office's errors: Cloud Logging's console,
    # opened on this service's logs (none locally).
    actions_enabled: bool
    logs_project: str | None
    logs_service: str | None


class SigninOut(BaseModel):
    url: str


class DevSessionIn(BaseModel):
    email: str


class AdminStaffOut(BaseModel):
    name: str
    email: str
    role: Role
    status: str
    last_seen_at: datetime | None


class AdminOfficeOut(BaseModel):
    id: str  # for searching the logs, where some lines name the office by it
    slug: str
    name: str
    status: str
    created_at: datetime
    hosts: list[str]
    owners: int
    staff: int
    pending: int
    projects: dict[str, int]
    storage: str
    writer_status: str | None
    reader_status: str | None
    drive_account: str | None
    last_activity_at: datetime | None
    emails_sent: int
    share_links: int
    downloads: int
    usage: dict[str, int]
    link_statuses: dict[str, int]
    project_types: dict[str, int]
    team: list[AdminStaffOut]


def _office(summary: offices.OfficeSummary) -> AdminOfficeOut:
    data = {k: v for k, v in vars(summary).items() if k not in ("id", "team")}
    return AdminOfficeOut(
        **data, id=str(summary.id), team=[AdminStaffOut(**vars(m)) for m in summary.team]
    )


def _settings(request: Request):
    return request.app.state.settings


def _secure(request: Request) -> bool:
    return _settings(request).deployed


def current_operator(request: Request) -> dict:
    """The signed-in operator's session, still on the allowlist, or 401."""
    _on_operator_host(request)
    try:
        session = keys.verify(
            _settings(request).app_secret, SESSION_PURPOSE, request.cookies.get(COOKIE, "")
        )
    except keys.BadToken:
        raise ApiError(401, ErrorCode.NOT_SIGNED_IN) from None
    if session.get("email") not in _settings(request).operator_allowlist:
        raise ApiError(401, ErrorCode.NOT_SIGNED_IN)
    return session


def operator_with_csrf(request: Request, session: dict = Depends(current_operator)) -> dict:
    sent = request.headers.get(CSRF_HEADER, "")
    if not secrets.compare_digest(sent, session.get("csrf", "")):
        raise ApiError(403, ErrorCode.CSRF_TOKEN_MISSING_OR_WRONG)
    return session


def _start_session(request: Request, response: Response, email: str) -> None:
    token = keys.sign(
        _settings(request).app_secret,
        SESSION_PURPOSE,
        {"email": email, "csrf": secrets.token_urlsafe(24)},
        SESSION_TTL,
    )
    response.set_cookie(
        COOKIE,
        token,
        max_age=SESSION_TTL,
        path="/",
        httponly=True,
        samesite="lax",
        secure=_secure(request),
    )


def _google(request: Request) -> GoogleSignIn:
    settings = _settings(request)
    if not (settings.google_oauth_client_id and settings.google_oauth_client_secret):
        raise ApiError(503, ErrorCode.SIGNIN_NOT_CONFIGURED)
    return GoogleSignIn(
        settings.google_oauth_client_id,
        settings.google_oauth_client_secret,
        settings.google_signin_redirect_uri,
    )


@router.get("/api/admin/me", responses=documented(401, 404))
async def me(request: Request, session: dict = Depends(current_operator)) -> OperatorOut:
    settings = _settings(request)
    return OperatorOut(
        actions_enabled=getattr(request.app.state, "operator_sessionmaker", None) is not None,
        email=session["email"],
        csrf_token=session["csrf"],
        logs_project=settings.google_cloud_project if settings.deployed else None,
        logs_service=os.environ.get("K_SERVICE") if settings.deployed else None,
    )


@router.post("/api/admin/signin", responses=documented(404, 503))
async def signin(request: Request, response: Response) -> SigninOut:
    """Google's sign-in address. The state, nonce and PKCE verifier stay in this
    browser, in a signed cookie for the callback: a return in another browser, or
    a replayed one, finds nothing to match."""
    _on_operator_host(request)
    google = _google(request)
    flow = {
        "state": secrets.token_urlsafe(24),
        "nonce": secrets.token_urlsafe(24),
        "verifier": new_verifier(),
    }
    response.set_cookie(
        FLOW_COOKIE,
        keys.sign(_settings(request).app_secret, FLOW_PURPOSE, flow, FLOW_TTL),
        max_age=FLOW_TTL,
        path=CALLBACK,
        httponly=True,
        samesite="lax",  # sent on Google's top-level redirect back
        secure=_secure(request),
    )
    return SigninOut(url=google.authorization_url(flow["state"], flow["nonce"], flow["verifier"]))


def _back(problem: str | None = None) -> RedirectResponse:
    # With the request ID its log line carries, so the page shows the support code.
    target = PAGE + (f"?entrar={problem}&ref={current_request_id()}" if problem else "")
    response = RedirectResponse(target, status_code=302)
    response.delete_cookie(FLOW_COOKIE, path=CALLBACK)
    return response


@router.get(CALLBACK, include_in_schema=False)
async def callback(request: Request) -> Response:
    """Google's one return address, for operators and for every office: an
    office's sign-in goes on to that office's own address (google_signin)."""
    _on_operator_host(request)
    if (office := google_signin.office_state(request)) is not None:
        return await google_signin.forward(request, office)
    settings = _settings(request)
    try:
        flow = keys.verify(settings.app_secret, FLOW_PURPOSE, request.cookies.get(FLOW_COOKIE, ""))
    except keys.BadToken:
        return _back("expirado")
    if not secrets.compare_digest(request.query_params.get("state", ""), flow["state"]):
        return _back("expirado")
    if request.query_params.get("error") or not request.query_params.get("code"):
        return _back("cancelado")
    who = attempts.device(request)  # as office sign-in (google_signin.TRIES)
    if not attempts.admit(google_signin.TRIES, who):
        return _back("tentativas")
    try:
        identity = await _google(request).identify(
            getattr(request.app.state, "http", None),  # set up at app start
            request.query_params["code"],
            flow["verifier"],
            flow["nonce"],
        )
    except SignInError as error:
        attempts.failed(google_signin.TRIES, who)
        log.error("operator sign-in failed: route=%s %s", CALLBACK, error.detail)
        return _back("falhou")
    attempts.succeeded(google_signin.TRIES, who)
    if identity.email not in settings.operator_allowlist:
        # Who tried is worth knowing; the page only says "not allowed".
        log.warning("operator sign-in refused for %s", identity.email)
        return _back("negado")
    response = _back()
    _start_session(request, response, identity.email)
    log.info("operator %s signed in", identity.email)
    return response


@router.post("/api/admin/signout", status_code=204, responses=documented(401, 403, 404))
async def signout(response: Response, _session: dict = Depends(operator_with_csrf)) -> None:
    response.delete_cookie(COOKIE, path="/")


@router.post("/api/admin/dev-session", status_code=204, responses=documented(404))
async def dev_session(body: DevSessionIn, request: Request, response: Response) -> None:
    """Local development and the browser tests, where Google can't be reached:
    sign in as an allowlisted email. Never anywhere deployed."""
    _on_operator_host(request)
    settings = _settings(request)
    email = body.email.strip().lower()
    if settings.deployed or email not in settings.operator_allowlist:
        raise ApiError(404, ErrorCode.PAGE_NOT_FOUND)
    _start_session(request, response, email)


@router.get("/api/admin/offices", responses=documented(401, 404))
async def office_list(
    request: Request, _session: dict = Depends(current_operator)
) -> list[AdminOfficeOut]:
    found = await offices.summaries(request.app.state.sessionmaker, datetime.now(UTC))
    return [_office(o) for o in found]


@router.get("/api/admin/offices/{slug}", responses=documented(401, 404))
async def office_detail(
    slug: str, request: Request, _session: dict = Depends(current_operator)
) -> AdminOfficeOut:
    found = await offices.summaries(request.app.state.sessionmaker, datetime.now(UTC), slug)
    if not found:
        raise ApiError(404, ErrorCode.PAGE_NOT_FOUND)
    return _office(found[0])


@router.post(
    "/api/admin/offices/{slug}/file-statistics", responses=documented(401, 403, 404, 409, 503)
)
async def file_statistics(
    slug: str,
    request: Request,
    response: Response,
    _session: dict = Depends(operator_with_csrf),
) -> FileStats:
    response.headers["Cache-Control"] = "private, no-store"
    async with request.app.state.sessionmaker() as db:
        tenant = await db.scalar(select(Tenant).where(Tenant.slug == slug))
        if tenant is None:
            raise ApiError(404, ErrorCode.PAGE_NOT_FOUND)
        await db.close()  # the registry read began an unscoped transaction
        scope_to_tenant(db.sync_session, tenant.id)
        try:
            async with asyncio.timeout(45):
                storage = await _storage(request, db)
                if storage is None:
                    raise ApiError(409, ErrorCode.DRIVE_NOT_CONNECTED)
                used, limit = None, None
                try:
                    connection = await db.scalar(select(StorageConnection))
                    if connection is not None and connection.kind is StorageKind.GOOGLE:
                        _connection, writer = await writer_for(request, db)
                        used, limit = await writer.storage()
                except (ApiError, ConnectError) as error:
                    log.error(
                        "admin quota: route=%s operation=quota tenant=%s detail=%s",
                        request.url.path,
                        tenant.id,
                        getattr(error, "detail", str(error)),
                    )
                result = await load_files(db, storage)
                result.account_used, result.account_limit = used, limit
                return result
        except (StorageError, TimeoutError) as error:
            log.error(
                "admin files: route=%s operation=file-statistics tenant=%s detail=%s",
                request.url.path,
                tenant.id,
                getattr(error, "detail", str(error)),
            )
            raise ApiError(503, ErrorCode.FILES_UNAVAILABLE) from None


class CreateTenantIn(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", max_length=63)
    name: str = Field(min_length=1, max_length=200)
    hostname: str = Field(max_length=253, pattern=r"^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")

    @field_validator("name")
    @classmethod
    def nonempty_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name required")
        return value.strip()

    @field_validator("hostname")
    @classmethod
    def usable_host(cls, value: str) -> str:
        if (
            value.startswith("www.")
            or "." not in value
            or any(
                not part or len(part) > 63 or part.startswith("-") or part.endswith("-")
                for part in value.split(".")
            )
        ):
            raise ValueError("hostname required")
        return value


class TenantActionIn(BaseModel):
    action: Literal["owner_link", "suspend", "restore", "delete"]
    confirmation: str = ""


class TenantActionOut(BaseModel):
    owner_url: str | None = None


def _action_sessionmaker(request: Request):
    maker = getattr(request.app.state, "operator_sessionmaker", None)
    if maker is None:
        raise ApiError(503, ErrorCode.OPERATOR_ACTIONS_UNAVAILABLE)
    return maker


def _action_failure(request: Request, tenant: str, error: Exception) -> ApiError:
    log.error(
        "operator action: route=%s operation=tenant-action tenant=%s detail=%s",
        request.url.path,
        tenant,
        error,
    )
    return ApiError(
        409 if isinstance(error, IntegrityError) else 503,
        ErrorCode.OPERATOR_ACTION_CONFLICT
        if isinstance(error, IntegrityError)
        else ErrorCode.OPERATOR_ACTION_FAILED,
    )


@router.post("/api/admin/offices", responses=documented(401, 403, 409, 422, 503))
async def create_tenant(
    body: CreateTenantIn,
    request: Request,
    response: Response,
    operator: dict = Depends(operator_with_csrf),
) -> TenantActionOut:
    response.headers["Cache-Control"] = "private, no-store"
    if body.hostname == _settings(request).operator_host:
        raise ApiError(409, ErrorCode.OPERATOR_ACTION_CONFLICT)
    try:
        async with _action_sessionmaker(request)() as db:
            tenant = Tenant(
                id=uuid.uuid4(), slug=body.slug, name=body.name, status=TenantStatus.ACTIVE
            )
            scope_to_tenant(db.sync_session, tenant.id)
            db.add(tenant)
            await db.flush()
            db.add(TenantDomain(tenant_id=tenant.id, hostname=body.hostname, is_primary=True))
            await db.flush()
            url = await actions.owner_link(db, tenant, _settings(request).local_site_port)
            actions.audit(db, operator["email"], "create", tenant, current_request_id())
            await db.commit()
            return TenantActionOut(owner_url=url)
    except SQLAlchemyError as error:
        raise _action_failure(request, body.slug, error) from None


@router.post("/api/admin/offices/{slug}/actions", responses=documented(401, 403, 404, 409, 503))
async def tenant_action(
    slug: str,
    body: TenantActionIn,
    request: Request,
    response: Response,
    operator: dict = Depends(operator_with_csrf),
) -> TenantActionOut:
    response.headers["Cache-Control"] = "private, no-store"
    try:
        async with _action_sessionmaker(request)() as db:
            tenant = await actions.scoped_tenant(db, slug)
            url = None
            if body.action == "owner_link":
                url = await actions.owner_link(db, tenant, _settings(request).local_site_port)
            elif body.action == "delete":
                await actions.delete_tenant(db, tenant, body.confirmation)
            else:
                tenant.status = (
                    TenantStatus.SUSPENDED if body.action == "suspend" else TenantStatus.ACTIVE
                )
            actions.audit(db, operator["email"], body.action, tenant, current_request_id())
            await db.commit()
            return TenantActionOut(owner_url=url)
    except SQLAlchemyError as error:
        raise _action_failure(request, slug, error) from None


async def _project_page(request: Request) -> Response:
    """The office's project at /admin, as the project pages' route would serve it."""
    tenant = current_tenant(request)
    async with request.app.state.sessionmaker() as db:
        scope_to_tenant(db.sync_session, tenant.id)
        staff = await optional_staff(request, Response(), db)
        return await pages.shell(request, PAGE.lstrip("/"), staff, tenant, db)


@router.get(PAGE, include_in_schema=False)
@router.get(PAGE + "/{rest:path}", include_in_schema=False)
async def page(request: Request, rest: str = "") -> Response:
    try:
        _on_operator_host(request)
    except ApiError:
        # On an office's address `/admin` is no dashboard: a project may have
        # that address (projects' addresses never have a second part).
        if rest or getattr(request.state, "tenant", None) is None:
            return PlainTextResponse("Not found", status_code=404)
        return await _project_page(request)
    shell = Path(_settings(request).frontend_dist) / "admin.html"
    if not shell.is_file():
        return PlainTextResponse(
            "The dashboard is not built. Run `make build` (or `make dev`).", status_code=503
        )
    return FileResponse(
        shell, headers={"Cache-Control": "no-cache", "Content-Security-Policy": POLICY}
    )
