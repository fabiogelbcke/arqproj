"""Sharing files by link (A37, plan section 15).

    POST /api/pages/{slug}/shares                make a link from files the page listed
    GET  /api/pages/{slug}/shares                staff: every link of the project
    POST /api/pages/{slug}/shares/mine           a device's own links, by their owner keys
    POST /api/pages/{slug}/shares/{id}/disable   "Desativar": staff, or the device that made it
    POST /api/pages/{slug}/shares/{id}/refresh   "Atualizar link": its files' newer versions
    GET  /share/{token}                          the supplier's page (its shell)
    GET  /api/share/{token}                      what it shows
    POST /api/share/{token}/unlock               a link's password, once per device
    GET  /api/share/{token}/files/{key}          one of its files
    GET  /api/share/{token}/zip                  "Baixar tudo": every file, one zip

Anyone who can see the page (the client, or staff) makes a link from the file
keys the page handed out, so nobody shares a file the page didn't show them. The
link keeps each file's storage identity: the exact version picked. Every visit
lists the project's stage folders as the page does and shows the link's files
still on it; renamed or moved to another stage, a file stays; hidden, trashed or
taken out of the project, it drops out, and the page says how many.

A token is looked up by its hash and kept encrypted, so staff can copy any link
again. The device that made a link gets an owner key for it (signed, never
stored), to list it, turn it off or update it later. A link may have a password,
typed once per device as a project page's (plan section 6).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import time
import uuid
from contextlib import aclosing
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import case, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.engine import get_tenant_session
from backend.documents import versions
from backend.documents.versions import shown_name
from backend.identity.models import User
from backend.identity.passwords import hash_password, verify_password
from backend.projects.models import Project, ProjectStage
from backend.security import keys
from backend.shares import zipped
from backend.shares.models import LABEL_MAX, ShareLink, ShareLinkFile
from backend.storage.base import StorageError, StorageItem
from backend.tenancy.resolve import CurrentTenant, current_tenant
from backend.web import attempts
from backend.web.auth import CSRF_HEADER, CurrentStaff, current_staff, optional_staff
from backend.web.errors import ApiError, ErrorCode, documented
from backend.web.page_files import (
    KEY_HOURS,
    NO_STORE,
    _disposition,
    _failure_page,
    _in_project,
    _kind,
    _still_listed,
    _storage,
    _storage_failure,
    open_key,
    read_key,
    stage_groups,
    streamed,
)
from backend.web.pages import (
    PAGE_HEADERS,
    PUBLISHED,
    OfficeOut,
    _head,
    _office,
    _offline,
    _origin,
    _page,
    _readable,
)
from backend.web.painel import CONTENT_SECURITY_POLICY, SHELL_CACHE
from backend.web.project_settings import PAGE_PASSWORD_MAX, PAGE_PASSWORD_MIN

log = logging.getLogger(__name__)
router = APIRouter()

TRIES = "share"  # new links: a few per device in 15 minutes (attempts.py)
SIZE_MAX = 300 * 1024 * 1024  # per link, counting every file (Fabio, 25 Oct 2026)
FILES_MAX = 200
DAY_BYTES_MAX = 5 * 1024**3  # downloads per link per day: bounds a leaked link
# A Google format exports as PDF with no size known beforehand: counted as this.
EXPORT_GUESS = 10 * 1024 * 1024
KEY_PURPOSE = "share-file"
OWNER_PURPOSE = "share-owner"
OWNER_DAYS = 3650  # the owner key lasts as long as the device keeps it
TOKEN_PURPOSE = "share-token"  # the token, encrypted, for staff to copy the link
UNLOCK_PURPOSE = "share-unlock"
UNLOCK_DAYS = 90  # as a project page's (plan section 6)
# The example project's link (frontend `EXAMPLE_SHARE`): its page is in the
# browser. A real token is 32 characters, so never this.
EXAMPLE_TOKEN = "exemplo"
# The supplier's page sends no referrer: the link itself is the secret.
SHARE_HEADERS = {**PAGE_HEADERS, "Referrer-Policy": "no-referrer"}


class ShareExpiry(StrEnum):
    WEEK = "7d"
    MONTH = "30d"
    NEVER = "never"


EXPIRY_DAYS = {ShareExpiry.WEEK: 7, ShareExpiry.MONTH: 30, ShareExpiry.NEVER: None}


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _owner_key(request: Request, link_id: uuid.UUID) -> str:
    return keys.sign(
        request.app.state.settings.app_secret,
        OWNER_PURPOSE,
        {"l": str(link_id)},
        OWNER_DAYS * 86400,
    )


def _url(request: Request, tenant: CurrentTenant, token: str) -> str:
    return f"{_origin(request, tenant)}/share/{token}"


def _unlock_cookie(link: ShareLink) -> str:
    return f"share-{link.id.hex[:16]}"


def _locked(request: Request, link: ShareLink) -> bool:
    """A link with a password, not yet typed on this device."""
    if link.password_hash is None:
        return False
    token = request.cookies.get(_unlock_cookie(link))
    if not token:
        return True
    try:
        found = keys.verify(request.app.state.settings.app_secret, UNLOCK_PURPOSE, token)
    except keys.BadToken:
        return True
    return found.get("l") != str(link.id)


def _owns(request: Request, owner: str | None) -> uuid.UUID | None:
    """The link an owner key names, or None for a missing or forged one."""
    if not owner:
        return None
    try:
        found = keys.verify(request.app.state.settings.app_secret, OWNER_PURPOSE, owner)
        return uuid.UUID(found["l"])
    except (keys.BadToken, KeyError, TypeError, ValueError):
        return None


def _staff_acting(request: Request, staff: CurrentStaff | None) -> CurrentStaff | None:
    """Staff acting as staff: signed in, with the session's CSRF token. Without
    it, a request counts as anyone's (the client's)."""
    if staff is None:
        return None
    sent = request.headers.get(CSRF_HEADER, "")
    return staff if hmac.compare_digest(sent, staff.csrf_token) else None


# -- where a link's files are now -----------------------------------------------------


@dataclass(frozen=True)
class Placed:
    """A file the project's page shows now, and where."""

    item: StorageItem
    position: int  # its stage's place on the page, from 1
    folder: str  # the folder it is listed in: the stage's, or a subfolder's
    newer: StorageItem | None  # its document's current version, when this is an older one


async def _placed(db: AsyncSession, storage, project: Project) -> dict[str, Placed]:
    """Every file the page shows now, by storage identity. Raises StorageError
    when any of it can't be read: a link then says "try again", never "gone"."""
    folders = list(
        await db.scalars(
            select(ProjectStage.folder_id)
            .where(ProjectStage.project_id == project.id)
            .order_by(ProjectStage.position)
        )
    )
    found: dict[str, Placed] = {}
    if storage is None or not any(folders):
        return found
    in_project = await _in_project(storage, project)
    for position, folder in enumerate(folders, start=1):
        if folder is None or folder not in in_project:
            continue
        for _group, parent, files in await stage_groups(storage, folder):
            for document in versions.group(files):
                current = document.current
                for _number, item in document.versions:
                    newer = None if item is current else current
                    found.setdefault(item.identity, Placed(item, position, parent, newer))
    return found


async def _files(db: AsyncSession, links: list[ShareLink]) -> dict[uuid.UUID, list[str]]:
    """Each link's files, by storage identity, in the order they were picked."""
    held: dict[uuid.UUID, list[str]] = {link.id: [] for link in links}
    if links:
        for row in await db.scalars(
            select(ShareLinkFile)
            .where(ShareLinkFile.link_id.in_(held))
            .order_by(ShareLinkFile.position)
        ):
            held[row.link_id].append(row.item_id)
    return held


# -- making and managing links (the project page) --------------------------------------


class ShareIn(BaseModel):
    files: list[str] = Field(min_length=1, max_length=FILES_MAX)  # the page's file keys
    label: str | None = Field(default=None, max_length=LABEL_MAX)  # "Para quem?"
    expiry: ShareExpiry
    password: str | None = Field(default=None, max_length=PAGE_PASSWORD_MAX)


class ShareOut(BaseModel):
    id: uuid.UUID
    label: str | None
    made_by: str | None  # the staff member's name; None: the client
    created_at: datetime
    expires_at: datetime | None  # None: never
    disabled: bool
    expired: bool
    files: int
    # Of its files, those the page still shows, and those with a newer version
    # there. None: Drive couldn't be read just now.
    available: int | None
    newer: int | None
    downloads: int
    last_download_at: datetime | None
    protected: bool  # has a password
    # Staff: the link, to copy again. None elsewhere, and for links made before
    # it was kept (0036).
    url: str | None = None


class ShareMadeOut(BaseModel):
    link: ShareOut
    url: str
    owner: str  # kept by the device that made it, to manage it later


class OwnedIn(BaseModel):
    owners: list[str] = Field(max_length=200)


class OwnerIn(BaseModel):
    owner: str | None = Field(default=None, max_length=500)


async def _described(
    db: AsyncSession,
    storage,
    project: Project,
    links: list[ShareLink],
    urls: tuple[Request, CurrentTenant] | None = None,
) -> list[ShareOut]:
    """The links as the lists show them; with `urls` (staff), each one's address."""
    held = await _files(db, links)
    try:
        placed = await _placed(db, storage, project) if storage is not None else None
    except StorageError as error:
        log.error(
            "shares: listing %s/%s failed: %s %s",
            project.tenant_id,
            project.id,
            error.problem,
            error.detail,
        )
        placed = None
    makers = {
        user.id: user.name
        for user in await db.scalars(
            select(User).where(User.id.in_({link.created_by for link in links if link.created_by}))
        )
    }
    now = datetime.now(UTC)
    out = []
    for link in links:
        items = held[link.id]
        out.append(
            ShareOut(
                id=link.id,
                label=link.label,
                made_by=makers.get(link.created_by) if link.created_by else None,
                created_at=link.created_at,
                expires_at=link.expires_at,
                disabled=link.disabled_at is not None,
                expired=link.expires_at is not None and link.expires_at <= now,
                files=len(items),
                available=None if placed is None else sum(i in placed for i in items),
                newer=(
                    None
                    if placed is None
                    else sum(1 for i in items if i in placed and placed[i].newer is not None)
                ),
                downloads=link.downloads,
                last_download_at=link.last_download_at,
                protected=link.password_hash is not None,
                url=_stored_url(link, *urls) if urls else None,
            )
        )
    return out


def _stored_url(link: ShareLink, request: Request, tenant: CurrentTenant) -> str | None:
    if link.token_encrypted is None:
        return None
    try:
        token = keys.decrypt(
            request.app.state.settings.app_secret, TOKEN_PURPOSE, link.token_encrypted
        )
    except keys.BadToken:  # a changed app secret: the list still shows, without it
        log.error("shares: the stored address of link %s can't be read", link.id)
        return None
    return _url(request, tenant, token)


@router.post(
    "/api/pages/{slug}/shares", status_code=201, responses=documented(403, 404, 409, 422, 429, 503)
)
async def make_share(
    request: Request,
    slug: str,
    body: ShareIn,
    staff: CurrentStaff | None = Depends(optional_staff),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> ShareMadeOut:
    project = await _readable(db, slug, staff, request)  # a locked page asks for its password
    who = attempts.device(request)
    if not attempts.admit(TRIES, who):
        raise ApiError(429, ErrorCode.TOO_MANY_ATTEMPTS)
    attempts.failed(TRIES, who)  # every request counts toward the limit
    # Only files this page listed for its current access (and not long ago).
    picked = list(dict.fromkeys(read_key(request, project, key)["i"] for key in body.files))
    storage = await _storage(request, db)
    if storage is None:
        raise ApiError(503, ErrorCode.FILES_UNAVAILABLE)
    try:
        placed = await _placed(db, storage, project)
    except StorageError as error:
        raise _storage_failure(error, project, "share") from None
    by_id = {p.item.id: p for p in placed.values()}
    if any(item_id not in by_id for item_id in picked):
        raise ApiError(409, ErrorCode.SHARE_FILES_CHANGED)  # hidden, moved out or gone since
    items = [by_id[item_id].item for item_id in picked]
    if sum(item.size or 0 for item in items) > SIZE_MAX:
        raise ApiError(422, ErrorCode.SHARE_TOO_LARGE)
    if body.password is not None and len(body.password) < PAGE_PASSWORD_MIN:
        raise ApiError(422, ErrorCode.PASSWORD_TOO_SHORT)
    label = (body.label or "").strip() or None
    days = EXPIRY_DAYS[body.expiry]
    token = secrets.token_urlsafe(24)
    acting = _staff_acting(request, staff)
    link = ShareLink(
        project_id=project.id,
        token_hash=_hash(token),
        token_encrypted=keys.encrypt(request.app.state.settings.app_secret, TOKEN_PURPOSE, token),
        password_hash=await hash_password(body.password) if body.password else None,
        label=label,
        created_by=acting.user_id if acting else None,
        expires_at=datetime.now(UTC) + timedelta(days=days) if days else None,
    )
    db.add(link)
    await db.flush()
    db.add_all(
        ShareLinkFile(link_id=link.id, item_id=item.identity, position=n)
        for n, item in enumerate(items)
    )
    await db.commit()
    await db.refresh(link)
    log.info("shares: link %s made for project %s, %s files", link.id, project.id, len(items))
    [shown] = await _described(db, storage, project, [link])
    return ShareMadeOut(
        link=shown,
        url=_url(request, tenant, token),
        owner=_owner_key(request, link.id),
    )


@router.get("/api/pages/{slug}/shares", responses=documented(401, 404))
async def project_shares(
    request: Request,
    slug: str,
    response: Response,
    staff: CurrentStaff = Depends(current_staff),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> list[ShareOut]:
    """Every link of the project, newest first, for staff, with its address."""
    project = await _readable(db, slug, staff, request)
    response.headers.update(NO_STORE)
    links = list(
        await db.scalars(
            select(ShareLink)
            .where(ShareLink.project_id == project.id)
            .order_by(ShareLink.created_at.desc())
        )
    )
    return await _described(db, await _storage(request, db), project, links, (request, tenant))


@router.post("/api/pages/{slug}/shares/mine", responses=documented(403, 404))
async def my_shares(
    request: Request,
    slug: str,
    body: OwnedIn,
    response: Response,
    staff: CurrentStaff | None = Depends(optional_staff),
    db: AsyncSession = Depends(get_tenant_session),
) -> list[ShareOut]:
    """The links this device made on this project, by the owner keys it kept."""
    project = await _readable(db, slug, staff, request)
    response.headers.update(NO_STORE)
    ids = {found for owner in body.owners if (found := _owns(request, owner))}
    links = list(
        await db.scalars(
            select(ShareLink)
            .where(ShareLink.project_id == project.id, ShareLink.id.in_(ids))
            .order_by(ShareLink.created_at.desc())
        )
    )
    return await _described(db, await _storage(request, db), project, links)


async def _managed(
    request: Request,
    db: AsyncSession,
    project: Project,
    link_id: uuid.UUID,
    staff: CurrentStaff | None,
    owner: str | None,
) -> ShareLink:
    """The project's link, if this request may manage it: staff, or the device
    that made it. Anyone else: "not found"."""
    link = await db.scalar(
        select(ShareLink)
        .where(ShareLink.id == link_id, ShareLink.project_id == project.id)
        .with_for_update()
    )
    allowed = _staff_acting(request, staff) is not None or _owns(request, owner) == link_id
    if link is None or not allowed:
        raise ApiError(404, ErrorCode.SHARE_NOT_FOUND)
    return link


@router.post("/api/pages/{slug}/shares/{link_id}/disable", responses=documented(403, 404))
async def disable_share(
    request: Request,
    slug: str,
    link_id: uuid.UUID,
    body: OwnerIn,
    staff: CurrentStaff | None = Depends(optional_staff),
    db: AsyncSession = Depends(get_tenant_session),
) -> ShareOut:
    project = await _readable(db, slug, staff, request)
    link = await _managed(request, db, project, link_id, staff, body.owner)
    if link.disabled_at is None:
        link.disabled_at = datetime.now(UTC)
        await db.commit()
        log.info("shares: link %s turned off", link.id)
    [shown] = await _described(db, await _storage(request, db), project, [link])
    return shown


@router.post("/api/pages/{slug}/shares/{link_id}/refresh", responses=documented(403, 404, 503))
async def refresh_share(
    request: Request,
    slug: str,
    link_id: uuid.UUID,
    body: OwnerIn,
    staff: CurrentStaff | None = Depends(optional_staff),
    db: AsyncSession = Depends(get_tenant_session),
) -> ShareOut:
    """ "Atualizar link": each file with a newer version on the page now serves
    that version, at the same address."""
    project = await _readable(db, slug, staff, request)
    link = await _managed(request, db, project, link_id, staff, body.owner)
    storage = await _storage(request, db)
    if storage is None:
        raise ApiError(503, ErrorCode.FILES_UNAVAILABLE)
    try:
        placed = await _placed(db, storage, project)
    except StorageError as error:
        raise _storage_failure(error, project, "share refresh") from None
    held = (await _files(db, [link]))[link.id]
    updated = []
    for item_id in held:
        newer = placed[item_id].newer if item_id in placed else None
        updated.append(newer.identity if newer is not None else item_id)
    updated = list(dict.fromkeys(updated))  # two versions of one document: one file
    if updated != held:
        await db.execute(delete(ShareLinkFile).where(ShareLinkFile.link_id == link.id))
        db.add_all(
            ShareLinkFile(link_id=link.id, item_id=item_id, position=n)
            for n, item_id in enumerate(updated)
        )
        link.files_updated_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(link)
        log.info("shares: link %s moved to newer versions", link.id)
    [shown] = await _described(db, storage, project, [link])
    return shown


# -- the supplier's page ---------------------------------------------------------------


async def _open_link(db: AsyncSession, token: str) -> tuple[ShareLink, Project]:
    """The link and its project, while it works: not turned off or expired, its
    project published and not deleted, the office's Drive connected. Anything
    else is one "not available", never told apart."""
    found = (
        await db.execute(
            select(ShareLink, Project)
            .join(Project, Project.id == ShareLink.project_id)
            .where(
                ShareLink.token_hash == _hash(token),
                ShareLink.disabled_at.is_(None),
                Project.deleted_at.is_(None),
                PUBLISHED,
            )
        )
    ).first()
    if found is None:
        raise ApiError(404, ErrorCode.SHARE_NOT_FOUND, headers=SHARE_HEADERS)
    link, project = found
    if link.expires_at is not None and link.expires_at <= datetime.now(UTC):
        raise ApiError(404, ErrorCode.SHARE_NOT_FOUND, headers=SHARE_HEADERS)
    if await _offline(db):
        raise ApiError(503, ErrorCode.PAGE_UNAVAILABLE, headers=SHARE_HEADERS)
    return link, project


class SharedFileOut(BaseModel):
    key: str
    name: str  # Drive's, with its version: "Planta v2.pdf", as it downloads
    kind: str  # "image", "pdf" or "other"
    size: int | None
    modified_at: datetime
    stage: str  # "02 Estudo preliminar"


class SharedOut(BaseModel):
    office: OfficeOut
    locale: str
    timezone: str
    project: str
    label: str | None
    expires_at: datetime | None
    files: list[SharedFileOut]
    unavailable: int  # files of the link the page no longer shows
    # "Baixar tudo": the zip's size, or None when a file's size isn't known before
    # it downloads (a Google format).
    zip_size: int | None = None


@router.get("/api/share/{token}", responses=documented(403, 404, 503))
async def shared(
    request: Request,
    token: str,
    response: Response,
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> SharedOut:
    link, project = await _open_link(db, token)
    response.headers.update({**SHARE_HEADERS, **NO_STORE})
    if _locked(request, link):
        raise ApiError(403, ErrorCode.SHARE_LOCKED, headers={**SHARE_HEADERS, **NO_STORE})
    held, shown, titles, _storage_view, office = await _shown(request, db, tenant, link, project)
    secret = request.app.state.settings.app_secret
    files = []
    for where in shown:
        key = keys.encrypt(
            secret,
            KEY_PURPOSE,
            json.dumps(
                {
                    "l": str(link.id),
                    "s": where.position,
                    "f": where.folder,
                    "i": where.item.id,
                    "exp": int(time.time()) + KEY_HOURS * 3600,
                }
            ),
        )
        files.append(
            SharedFileOut(
                key=key,
                name=shown_name(where.item),
                kind=_kind(where.item),
                size=where.item.size,
                modified_at=where.item.modified_at,
                stage=titles[where.position],
            )
        )
    return SharedOut(
        office=office,
        locale=tenant.locale.value,
        timezone=tenant.timezone,
        project=project.name,
        label=link.label,
        expires_at=link.expires_at,
        files=files,
        unavailable=len(held) - len(files),
        zip_size=zipped.length(_entries(shown, titles, tenant)) if shown else None,
    )


async def _shown(
    request: Request, db: AsyncSession, tenant: CurrentTenant, link: ShareLink, project: Project
) -> tuple[list[str], list[Placed], dict[int, str], object, OfficeOut]:
    """The link's files, those the page shows now (in the order picked), each
    stage's "02 Estudo preliminar" by its place, the storage view that listed
    them (its checks kept, for the downloads) and the office."""
    storage = await _storage(request, db)
    try:
        placed = await _placed(db, storage, project) if storage is not None else {}
    except StorageError as error:
        failure = _storage_failure(error, project, "share listing")
        failure.headers = SHARE_HEADERS
        raise failure from None
    page = await _page(db, tenant, project, "")
    titles = {stage.position: f"{stage.position:02d} {stage.title}" for stage in page.stages}
    held = (await _files(db, [link]))[link.id]
    return held, [placed[i] for i in held if i in placed], titles, storage, page.office


def _entries(
    shown: list[Placed], titles: dict[int, str], tenant: CurrentTenant
) -> list[zipped.Entry]:
    """The zip's contents: a folder per stage, the files under Drive's names
    (a "/" in either kept from making folders), dated in the office's time."""
    zone = ZoneInfo(tenant.timezone)
    names = zipped.unique_names(
        [
            f"{zipped.part(titles[where.position])}/{zipped.part(shown_name(where.item))}"
            for where in shown
        ]
    )
    return [
        zipped.Entry(name, where.item.size, where.item.modified_at.astimezone(zone))
        for name, where in zip(names, shown, strict=True)
    ]


class UnlockIn(BaseModel):
    password: str = Field(max_length=200)


@router.post("/api/share/{token}/unlock", status_code=204, responses=documented(401, 404, 429))
async def unlock_share(
    request: Request,
    token: str,
    body: UnlockIn,
    db: AsyncSession = Depends(get_tenant_session),
) -> Response:
    """The supplier types the link's password once per device."""
    challenge = {**SHARE_HEADERS, **NO_STORE}  # never stored (plan section 6)
    link, _project = await _open_link(db, token)
    if link.password_hash is None:
        raise ApiError(404, ErrorCode.SHARE_NOT_FOUND, headers=challenge)
    who, key = attempts.device(request), f"share:{link.id}"
    if not attempts.admit(key, who):  # reserved before the (slow) hash check
        raise ApiError(429, ErrorCode.TOO_MANY_ATTEMPTS, headers=challenge)
    try:
        right = await verify_password(link.password_hash, body.password)
    except BaseException:
        attempts.failed(key, who)
        raise
    if not right:
        attempts.failed(key, who)
        raise ApiError(401, ErrorCode.WRONG_SHARE_PASSWORD, headers=challenge)
    attempts.succeeded(key, who)
    response = Response(status_code=204, headers=challenge)
    response.set_cookie(
        _unlock_cookie(link),
        keys.sign(
            request.app.state.settings.app_secret,
            UNLOCK_PURPOSE,
            {"l": str(link.id)},
            UNLOCK_DAYS * 86400,
        ),
        max_age=UNLOCK_DAYS * 86400,
        path="/",
        httponly=True,
        samesite="lax",
        secure=request.app.state.settings.deployed,
    )
    return response


def _download_failure(tenant: CurrentTenant, error: ApiError, back: str) -> Response:
    """A download that can't go, as a short page in the office's language."""
    if error.code in (ErrorCode.SHARE_NOT_FOUND, ErrorCode.SHARE_LOCKED):
        return _failure_page(
            tenant, "", error.code, 404 if error.code is ErrorCode.SHARE_NOT_FOUND else 403, back
        )
    if error.code is ErrorCode.SHARE_DAILY_LIMIT:
        return _failure_page(tenant, "", error.code, 429, back)
    if error.code in (ErrorCode.FILES_UNAVAILABLE, ErrorCode.PAGE_UNAVAILABLE):
        return _failure_page(tenant, "", ErrorCode.FILES_UNAVAILABLE, 503, back)
    return _failure_page(tenant, "", ErrorCode.FILE_NOT_FOUND, 404, back)


@router.get("/api/share/{token}/zip", include_in_schema=False)
async def shared_zip(
    request: Request,
    token: str,
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> Response:
    """ "Baixar tudo": the link's files as they are on the page now, a folder per
    stage, written while it downloads. Counted against the day as one download of
    its whole size."""
    back = f"/share/{token}"
    try:
        link, project = await _open_link(db, token)
        if _locked(request, link):
            raise ApiError(403, ErrorCode.SHARE_LOCKED)
        _held, shown, titles, storage, _office_shown = await _shown(
            request, db, tenant, link, project
        )
        if not shown:
            raise ApiError(404, ErrorCode.FILE_NOT_FOUND)
        entries = _entries(shown, titles, tenant)
        size = zipped.length(entries)
        # Its exact length; with a Google format (no size beforehand), that one is
        # a guess and the rest count as they are.
        guessed = sum(EXPORT_GUESS if e.size is None else e.size for e in entries)
        await _count(db, link, size if size is not None else guessed)
    except ApiError as error:
        return _download_failure(tenant, error, back)
    await db.close()  # before the bytes flow (plan section 15)

    # The one upstream download open now, closed however the zip ends (the
    # supplier cancelling included: storage.Download's rule).
    current: list = []

    async def open_file(index: int):
        download = await storage.download(shown[index].item)
        current.append(download)

        async def chunks():
            async for chunk in download.chunks:
                yield chunk
            current.remove(download)
            await download.aclose()

        return chunks()

    async def body():
        try:
            async with aclosing(zipped.stream(entries, open_file)) as parts:
                async for chunk in parts:
                    yield chunk
        except (StorageError, zipped.SizeChanged) as error:  # the browser sees a cut download
            log.error(
                "shares: zip of link %s broke off for %s/%s: %s",
                link.id,
                project.tenant_id,
                project.id,
                getattr(error, "detail", "") or error,
            )
            raise
        finally:
            for download in current:
                await download.aclose()

    headers = {
        **SHARE_HEADERS,
        **NO_STORE,
        "Content-Disposition": _disposition(f"{project.name}.zip", inline=False),
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; sandbox",
    }
    if size is not None:
        headers["Content-Length"] = str(size)
    log.info("shares: zip of link %s, %s files", link.id, len(entries))
    return StreamingResponse(body(), media_type="application/zip", headers=headers)


@router.get("/api/share/{token}/files/{key}", include_in_schema=False)
async def shared_file(
    request: Request,
    token: str,
    key: str,
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> Response:
    back = f"/share/{token}"
    try:
        link, project = await _open_link(db, token)
        if _locked(request, link):
            raise ApiError(403, ErrorCode.SHARE_LOCKED)
        found = open_key(request, KEY_PURPOSE, key)
        if found.get("l") != str(link.id):
            raise ApiError(404, ErrorCode.FILE_NOT_FOUND)
        storage = await _storage(request, db)
        if storage is None:
            raise ApiError(404, ErrorCode.FILE_NOT_FOUND)
        try:
            if not await _still_listed(db, storage, project, found):
                raise ApiError(404, ErrorCode.FILE_NOT_FOUND)  # moved, hidden or removed
            item = await storage.get(found["i"])
        except StorageError as error:
            raise _storage_failure(error, project, "share open") from None
        if item.identity not in (await _files(db, [link]))[link.id]:
            raise ApiError(404, ErrorCode.FILE_NOT_FOUND)  # the link moved to a newer version
        await _count(db, link, item.size if item.size is not None else EXPORT_GUESS)
        try:
            download = await storage.download(item)
        except StorageError as error:
            raise _storage_failure(error, project, "share download") from None
    except ApiError as error:
        return _download_failure(tenant, error, back)
    await db.close()  # before the bytes flow (plan section 15)
    answer = streamed(project, item, download, inline=False)
    answer.headers["Referrer-Policy"] = "no-referrer"
    return answer


async def _count(db: AsyncSession, link: ShareLink, size: int) -> None:
    """A download's size against the link's day, before any byte flows: past the
    daily cap, refused. Counted when it starts, so a cut download still counts.
    One conditional update, so downloads at the same moment can't both slip under
    the cap."""
    today = datetime.now(UTC).date()
    spent = case((ShareLink.day == today, ShareLink.day_bytes), else_=0)
    counted = await db.execute(
        update(ShareLink)
        .where(ShareLink.id == link.id, spent + size <= DAY_BYTES_MAX)
        .values(
            day=today,
            day_bytes=spent + size,
            downloads=ShareLink.downloads + 1,
            last_download_at=func.now(),
        )
        .returning(ShareLink.id)
    )
    if counted.first() is None:
        log.warning("shares: link %s reached its daily download limit", link.id)
        raise ApiError(429, ErrorCode.SHARE_DAILY_LIMIT)
    await db.commit()


@router.get("/share/{token}", include_in_schema=False)
async def share_shell(
    request: Request,
    token: str,
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> Response:
    """The client page's bundle, which shows the supplier's page at this address.
    Its link preview names only the office."""
    shell_file = Path(request.app.state.settings.frontend_dist) / "client.html"
    if not shell_file.is_file():
        return PlainTextResponse(
            "The client page is not built. Run `make build` (or `make dev`).", status_code=503
        )
    try:
        if token != EXAMPLE_TOKEN:  # the example project's, shown from the browser
            await _open_link(db, token)
        status = 200
    except ApiError as error:
        status = error.status_code
    office = (await _office(db, tenant)).name
    tags = {"robots": "noindex", "og:title": office, "og:type": "website"}
    document = shell_file.read_text("utf-8").replace("<!--page-head-->", _head(tags, office))
    return Response(
        document,
        status_code=status,
        media_type="text/html; charset=utf-8",
        headers={
            "Cache-Control": SHELL_CACHE,
            "Content-Security-Policy": CONTENT_SECURITY_POLICY,
            **SHARE_HEADERS,
        },
    )
