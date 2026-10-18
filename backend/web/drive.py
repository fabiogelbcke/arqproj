"""Connecting an office's Google Drive from the painel (owners only).

    POST   /api/drive/connect    start: returns Google's sign-in address
    GET    /api/drive/callback   Google returns here (see below)
    GET    /api/drive            the office's storage: kind, account, health
    GET    /api/drive/space      the Google account's space, used and in all
    DELETE /api/drive            forget the office's grant (files stay in Drive)

Google only accepts return addresses registered in the app registration, and an
address per office cannot be registered, so there is **one shared return
address** (GOOGLE_OAUTH_REDIRECT_URI; locally http://127.0.0.1:5173). The
sign-in carries a signed, short-lived `state` naming the office address that
started it. Arriving at the shared address, the request is forwarded, unchanged,
to that office's address (only if it is registered to that office); there the
signed-in owner's session and a one-time nonce cookie are checked, and the
connection is completed.
"""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.engine import get_tenant_session
from backend.db.isolation import scope_to_tenant
from backend.identity.models import Role
from backend.office.models import OfficeProfile
from backend.projects.models import Project, ProjectStage
from backend.security import keys
from backend.storage.base import StorageError
from backend.storage.google import OfficeDrive
from backend.storage.google_connect import (
    ROOT_FOLDER_NAME,
    ConnectError,
    ConnectProblem,
    DriveWriter,
    OAuthClient,
)
from backend.storage.models import ReaderStatus, StorageConnection, StorageKind, WriterStatus
from backend.tenancy.models import Locale
from backend.tenancy.resolve import CurrentTenant, current_tenant, normalize_host, resolve
from backend.web.auth import CurrentStaff, current_staff, require_csrf
from backend.web.errors import ApiError, ErrorCode, documented
from backend.web.request_id import current_request_id

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

STATE_PURPOSE = "drive-connect-state"
TOKEN_PURPOSE = "drive-refresh-token"
NONCE_COOKIE = "drive_connect"
STATE_TTL = 600  # seconds: long enough to sign in, short enough to be useless later
SETTINGS_PAGE = "/painel/configuracoes/drive"


class ConnectOut(BaseModel):
    url: str


class ConnectIn(BaseModel):
    # Another Google account than the one whose folder the office has: start
    # afresh in it (the owner confirmed the warning that files don't come along).
    fresh: bool = False


class DriveOut(BaseModel):
    kind: StorageKind | None  # None: not connected yet
    writer_status: WriterStatus
    reader_status: ReaderStatus
    account_email: str | None
    folder_url: str | None
    can_manage: bool  # owners connect and disconnect; members only see
    # A folder from an earlier connection: reconnecting the same account keeps it;
    # another account starts afresh (the screen warns before).
    has_folder: bool


class SpaceOut(BaseModel):
    used: int  # bytes
    total: int | None  # None: no limit set by Google (Workspace pooled storage)


def _require_owner(staff: CurrentStaff) -> None:
    if staff.role is not Role.OWNER:
        raise ApiError(403, ErrorCode.OWNER_ONLY)


def _oauth(request: Request) -> OAuthClient:
    settings = request.app.state.settings
    if not settings.drive_configured:
        raise ApiError(503, ErrorCode.DRIVE_NOT_CONFIGURED)
    return OAuthClient(
        settings.google_oauth_client_id,
        settings.google_oauth_client_secret,
        settings.google_oauth_redirect_uri,
    )


async def _connection(db: AsyncSession) -> StorageConnection | None:
    return await db.scalar(select(StorageConnection))


@router.get("/drive", responses=documented(401))
async def drive_status(
    staff: CurrentStaff = Depends(current_staff), db: AsyncSession = Depends(get_tenant_session)
) -> DriveOut:
    connection = await _connection(db)
    google = connection is not None and connection.kind is StorageKind.GOOGLE
    return DriveOut(
        kind=connection.kind if connection else None,
        writer_status=connection.writer_status if connection else WriterStatus.NONE,
        reader_status=connection.reader_status if connection else ReaderStatus.UNKNOWN,
        account_email=connection.account_email if connection else None,
        folder_url=(
            f"https://drive.google.com/drive/folders/{connection.root_id}" if google else None
        ),
        can_manage=staff.role is Role.OWNER,
        has_folder=google and bool(connection.root_id),
    )


@router.get("/drive/space", responses=documented(401, 409, 503))
async def drive_space(
    request: Request,
    _staff: CurrentStaff = Depends(current_staff),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> SpaceOut:
    """How full the office's Google account is, as the old site showed: asked
    of Google on each visit to the Drive settings, never stored."""
    _connection, writer = await writer_for(request, db)
    try:
        used, total = await writer.storage()
    except ConnectError as error:
        log.error("drive space: route=/api/drive/space tenant=%s %s", tenant.slug, error.detail)
        raise ApiError(503, ErrorCode.DRIVE_CONNECT_FAILED) from None
    return SpaceOut(used=used, total=total)


@router.post("/drive/connect", responses=documented(401, 403, 503))
async def connect(
    request: Request,
    response: Response,
    body: ConnectIn | None = None,
    staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
) -> ConnectOut:
    _require_owner(staff)
    oauth = _oauth(request)
    nonce = secrets.token_urlsafe(24)
    origin = f"{request.url.scheme}://{request.headers['host']}"
    state = keys.sign(
        request.app.state.settings.app_secret,
        STATE_PURPOSE,
        {
            "origin": origin,
            "tenant": str(tenant.id),
            "nonce": nonce,
            "fresh": bool(body and body.fresh),
        },
        STATE_TTL,
    )
    response.set_cookie(
        NONCE_COOKIE,
        nonce,
        max_age=STATE_TTL,
        path="/api/drive/callback",
        httponly=True,
        samesite="lax",  # sent on Google's top-level redirect back
        secure=request.app.state.settings.deployed,
    )
    return ConnectOut(url=oauth.authorization_url(state))


@router.get("/drive/callback", include_in_schema=False)
async def callback(request: Request) -> Response:
    settings = request.app.state.settings
    try:
        state = keys.verify(
            settings.app_secret, STATE_PURPOSE, request.query_params.get("state", "")
        )
    except keys.BadToken:
        return _back(request, ErrorCode.DRIVE_LINK_INVALID)
    origin = state["origin"]
    tenant = getattr(request.state, "tenant", None)

    # Arriving at the shared return address: forward to the office that started.
    if tenant is None or str(tenant.id) != state["tenant"]:
        async with request.app.state.sessionmaker() as session:
            resolution = await resolve(session, urlsplit(origin).netloc)
        if resolution is None or str(resolution.tenant.id) != state["tenant"]:
            log.warning("drive callback for an address not registered to its office")
            return Response("Not found", status_code=404, media_type="text/plain")
        return RedirectResponse(f"{origin}/api/drive/callback?{request.url.query}", 302)

    # On the office's own address: the owner who started, and only once.
    nonce = request.cookies.get(NONCE_COOKIE, "")
    if not secrets.compare_digest(nonce, state["nonce"]):
        return _back(request, ErrorCode.DRIVE_LINK_INVALID)
    if request.query_params.get("error"):  # e.g. the owner pressed "Cancel" at Google
        return _back(request, ErrorCode.DRIVE_DENIED)
    async with request.app.state.sessionmaker() as db:
        scope_to_tenant(db.sync_session, tenant.id)
        try:
            staff = await current_staff(request, Response(), db)
        except ApiError:
            return _back(request, ErrorCode.NOT_SIGNED_IN)
        if staff.role is not Role.OWNER:
            return _back(request, ErrorCode.OWNER_ONLY)
        try:
            await _complete(
                request,
                db,
                staff,
                request.query_params.get("code", ""),
                fresh=state.get("fresh", False),
                locale=tenant.locale,
            )
        except ConnectError as error:
            log.error(
                "drive connect failed for tenant %s: %s %s",
                tenant.slug,
                error.problem,
                error.detail,
            )
            code = {
                ConnectProblem.SHARE_FAILED: ErrorCode.DRIVE_SHARE_FAILED,
                ConnectProblem.OTHER_ACCOUNT: ErrorCode.DRIVE_OTHER_ACCOUNT,
            }.get(error.problem, ErrorCode.DRIVE_CONNECT_FAILED)
            return _back(request, code)
    done = RedirectResponse(f"{SETTINGS_PAGE}?resultado=conectado", 302)
    done.delete_cookie(NONCE_COOKIE, path="/api/drive/callback")
    return done


async def _complete(
    request: Request,
    db: AsyncSession,
    staff: CurrentStaff,
    code: str,
    *,
    fresh: bool = False,
    locale: Locale = Locale.PT_BR,
) -> None:
    settings = request.app.state.settings
    http = request.app.state.http
    oauth = _oauth(request)
    refresh_token, access_token = await oauth.exchange(http, code)
    writer = DriveWriter(http, access_token)
    connection = await _connection(db)
    reader = settings.drive_reader_identity

    root = None
    switching = False
    if connection and connection.kind is StorageKind.GOOGLE and connection.root_id:
        # Reconnecting: the office's folder holds its projects' files, so the same
        # account keeps it. Another account can't reach it (the app sees only what
        # it made with that account): unless the owner chose to start afresh after
        # the warning, nothing changes and they are told (plan section 9).
        if await writer.can_open(connection.root_id):
            root = connection.root_id
        elif not fresh:
            raise ConnectError(ConnectProblem.OTHER_ACCOUNT)
        else:
            switching = True
    if root is None:
        root = await writer.create_folder(ROOT_FOLDER_NAME)
        try:
            # While it is empty: the only moment sharing works (plan section 9).
            await writer.share_with_reader(root, reader)
            if switching:
                await _start_afresh(db, writer, root, locale)
        except ConnectError:
            await db.rollback()
            await writer.trash(root)  # never leave a folder the reader cannot see
            raise

    # The old account's grant, let go of only once the switch is saved.
    old_token = connection.writer_token if switching and connection else None
    if connection is None:
        connection = StorageConnection(kind=StorageKind.GOOGLE)
        db.add(connection)
    connection.kind = StorageKind.GOOGLE
    connection.root_id = root
    connection.reader_identity = reader
    connection.account_email = await writer.account_email()
    connection.writer_token = keys.encrypt(settings.app_secret, TOKEN_PURPOSE, refresh_token)
    connection.writer_status = WriterStatus.CONNECTED
    connection.connected_by = staff.user_id
    connection.checked_at = datetime.now(UTC)
    connection.reader_status = await _reader_status(request, root)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        if switching:
            await writer.trash(root)  # all or nothing: the new account's folders go too
        raise
    if old_token:
        # Still connected to the old account: let go of its grant, as disconnecting does.
        try:
            old = keys.decrypt(settings.app_secret, TOKEN_PURPOSE, old_token)
            await oauth.revoke(http, old)
        except keys.BadToken:
            log.warning("old Drive grant could not be decrypted; not revoked")


async def _start_afresh(db: AsyncSession, writer: DriveWriter, root: str, locale: Locale) -> None:
    """Another Google account, chosen after the warning: the old account's files
    stay where they are, out of this account's reach. Every project and stage gets
    an empty folder in the new one; covers and the logo (files in the old account)
    are dropped, and each project's next scan only notes what is there, so no
    client is emailed about files moved across by hand (files there get new ids,
    so the old account's in `project_files_seen` never match). Not committed: on a
    failure the caller rolls back and trashes the new folder (with these in it)."""
    from backend.web.page_stages import _folder_name, _title  # page code imports this module

    projects = (await db.scalars(select(Project).where(Project.deleted_at.is_(None)))).all()
    for project in projects:
        project.folder_id = await writer.create_folder(project.name, root)
        project.cover_file_id = project.cover_type = project.cover_folder_id = None
        project.files_scanned_at = None
        stages = await db.scalars(
            select(ProjectStage)
            .where(ProjectStage.project_id == project.id)
            .order_by(ProjectStage.position)
        )
        for stage in stages:
            title = await _title(db, stage, locale)
            stage.folder_id = await writer.create_folder(
                _folder_name(stage.position, title), project.folder_id
            )
    office = await db.scalar(select(OfficeProfile))
    if office is not None:
        office.logo_file_id = office.logo_type = office.logo_png_file_id = None
        office.logo_dark_file_id = office.logo_dark_type = office.brand_folder_id = None


async def _reader_status(request: Request, root: str) -> ReaderStatus:
    try:
        await OfficeDrive(request.app.state.google, root).list_folder(root)
    except StorageError as error:
        log.warning("reader cannot open the office folder: %s %s", error.problem, error.detail)
        return ReaderStatus.NO_ACCESS
    return ReaderStatus.OK


@router.delete("/drive", status_code=204, responses=documented(401, 403))
async def disconnect(
    request: Request,
    staff: CurrentStaff = Depends(require_csrf),
    db: AsyncSession = Depends(get_tenant_session),
) -> None:
    _require_owner(staff)
    connection = await _connection(db)
    if connection is None or connection.writer_token is None:
        return
    try:
        token = keys.decrypt(
            request.app.state.settings.app_secret, TOKEN_PURPOSE, connection.writer_token
        )
        if request.app.state.settings.drive_configured:
            await _oauth(request).revoke(request.app.state.http, token)
    except keys.BadToken:
        log.warning("stored Drive token could not be decrypted; forgetting it")
    # Forget the grant; the folder and files stay in Drive, and pages keep reading
    # through the reader identity.
    connection.writer_token = None
    connection.writer_status = WriterStatus.NONE
    await db.commit()


async def writer_for(request: Request, db: AsyncSession) -> tuple[StorageConnection, DriveWriter]:
    """The office's own grant, refreshed for use now. A refused grant marks the
    connection expired (the painel then asks to reconnect)."""
    connection = await _connection(db)
    if (
        connection is None
        or connection.kind is not StorageKind.GOOGLE
        or connection.writer_status is not WriterStatus.CONNECTED
    ):
        raise ApiError(409, ErrorCode.DRIVE_NOT_CONNECTED)
    settings = request.app.state.settings
    try:
        refresh = keys.decrypt(settings.app_secret, TOKEN_PURPOSE, connection.writer_token)
        access = await _oauth(request).access_token(request.app.state.http, refresh)
    except ConnectError as error:
        if error.problem is not ConnectProblem.EXPIRED:
            log.error(
                "Google token service unavailable: route=%s tenant=%s %s",
                request.url.path,
                connection.tenant_id,
                error.detail,
            )
            raise ApiError(503, ErrorCode.DRIVE_CONNECT_FAILED) from None
        log.error("office Drive grant refused: %s", error.detail)
        connection.writer_status = WriterStatus.EXPIRED
        connection.checked_at = datetime.now(UTC)
        await db.commit()
        raise ApiError(409, ErrorCode.DRIVE_EXPIRED) from None
    except keys.BadToken as error:
        log.error("office Drive grant refused: %r", getattr(error, "detail", error))
        connection.writer_status = WriterStatus.EXPIRED
        connection.checked_at = datetime.now(UTC)
        await db.commit()
        raise ApiError(409, ErrorCode.DRIVE_EXPIRED) from None
    return connection, DriveWriter(request.app.state.http, access)


def _back(request: Request, code: ErrorCode) -> Response:
    """To the settings page with an error code the screen translates."""
    host = normalize_host(request.headers.get("host"))
    if getattr(request.state, "tenant", None) is None or host is None:
        return Response("Not found", status_code=404, media_type="text/plain")
    # The request ID the log line carries, so the screen can show the support code.
    return RedirectResponse(f"{SETTINGS_PAGE}?erro={code.value}&ref={current_request_id()}", 302)
