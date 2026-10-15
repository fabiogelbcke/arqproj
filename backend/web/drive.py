"""Connecting an office's Google Drive from the painel (owners only).

    POST   /api/drive/connect    start: returns Google's sign-in address
    GET    /api/drive/callback   Google returns here (see below)
    GET    /api/drive            the office's storage: kind, account, health
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
from backend.tenancy.resolve import CurrentTenant, current_tenant, normalize_host, resolve
from backend.web.auth import CurrentStaff, current_staff, require_csrf
from backend.web.errors import ApiError, ErrorCode, documented

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

STATE_PURPOSE = "drive-connect-state"
TOKEN_PURPOSE = "drive-refresh-token"
NONCE_COOKIE = "drive_connect"
STATE_TTL = 600  # seconds: long enough to sign in, short enough to be useless later
SETTINGS_PAGE = "/painel/configuracoes/drive"


class ConnectOut(BaseModel):
    url: str


class DriveOut(BaseModel):
    kind: StorageKind | None  # None: not connected yet
    writer_status: WriterStatus
    reader_status: ReaderStatus
    account_email: str | None
    folder_url: str | None
    can_manage: bool  # owners connect and disconnect; members only see


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
    )


@router.post("/drive/connect", responses=documented(401, 403, 503))
async def connect(
    request: Request,
    response: Response,
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
        {"origin": origin, "tenant": str(tenant.id), "nonce": nonce},
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
            await _complete(request, db, staff, request.query_params.get("code", ""))
        except ConnectError as error:
            log.error(
                "drive connect failed for tenant %s: %s %s",
                tenant.slug,
                error.problem,
                error.detail,
            )
            code = (
                ErrorCode.DRIVE_SHARE_FAILED
                if error.problem is ConnectProblem.SHARE_FAILED
                else ErrorCode.DRIVE_CONNECT_FAILED
            )
            return _back(request, code)
    done = RedirectResponse(f"{SETTINGS_PAGE}?resultado=conectado", 302)
    done.delete_cookie(NONCE_COOKIE, path="/api/drive/callback")
    return done


async def _complete(request: Request, db: AsyncSession, staff: CurrentStaff, code: str) -> None:
    settings = request.app.state.settings
    http = request.app.state.http
    oauth = _oauth(request)
    refresh_token, access_token = await oauth.exchange(http, code)
    writer = DriveWriter(http, access_token)
    connection = await _connection(db)
    reader = settings.drive_reader_identity

    root = None
    if connection and connection.kind is StorageKind.GOOGLE and connection.root_id:
        # Reconnecting: keep the folder if this grant still reaches it.
        if await writer.can_open(connection.root_id):
            root = connection.root_id
    if root is None:
        root = await writer.create_folder(ROOT_FOLDER_NAME)
        try:
            # While it is empty: the only moment sharing works (plan section 9).
            await writer.share_with_reader(root, reader)
        except ConnectError:
            await writer.trash(root)  # never leave a folder the reader cannot see
            raise

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
    await db.commit()


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


def _back(request: Request, code: ErrorCode) -> Response:
    """To the settings page with an error code the screen translates."""
    host = normalize_host(request.headers.get("host"))
    if getattr(request.state, "tenant", None) is None or host is None:
        return Response("Not found", status_code=404, media_type="text/plain")
    return RedirectResponse(f"{SETTINGS_PAGE}?erro={code.value}", 302)
