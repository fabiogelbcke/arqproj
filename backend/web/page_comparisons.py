"""Before-and-after comparisons on the project page's edit mode (A46).

    POST /api/projects/{id}/stages/{n}/comparisons   open both sides' uploads
    POST /api/pages/{slug}/comparisons/{key}/edit    its title and labels: renames both sides
    POST /api/pages/{slug}/comparisons/{key}/hide    "Ocultar do cliente": both sides
    POST /api/pages/{slug}/comparisons/{key}/move    "Mover para…": both sides

A comparison is two images named for it (backend/documents/comparisons.py),
nothing stored: "Comparação antes e depois" uploads both with those names, as
any upload goes (A31), and the page pairs them when it lists the folder. `key`
is the comparison card's: its "before" side's current version. Each change
acts on every version of both sides, so the two stay one comparison; and only
if the app made all of them (drive.file), checked before any is changed. A new
version of one side is an ordinary "Enviar nova versão" (page_uploads).
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.analytics import capture
from backend.db.engine import get_tenant_session
from backend.documents import comparisons, versions
from backend.documents.comparisons import Side
from backend.projects.creation import LocalFolders
from backend.projects.models import Project, ProjectStage
from backend.storage.base import StorageError
from backend.storage.google_connect import ConnectError
from backend.tenancy.resolve import CurrentTenant, current_tenant
from backend.web.auth import CurrentStaff, require_csrf
from backend.web.errors import ApiError, ErrorCode, documented
from backend.web.page_files import INLINE_IMAGES, _in_project, _is_image, _item_at
from backend.web.page_uploads import (
    UPLOAD_MAX,
    _changeable,
    _clean,
    _documents,
    _listing_failed,
    _section,
    _stage_for_upload,
    local_upload_url,
    upload_origin,
)
from backend.web.pages import _readable
from backend.web.projects import _folders

log = logging.getLogger(__name__)
router = APIRouter()


class SideIn(BaseModel):
    name: str = Field(max_length=255)  # as chosen: only its extension is kept
    size: int = Field(ge=0)
    mime_type: str = Field(max_length=255)


class ComparisonIn(BaseModel):
    # The page's: stages may have moved since it loaded (plan section 7).
    row_version: int
    folder: str | None = Field(default=None, max_length=255)  # a section, as for uploads
    title: str = Field(max_length=255)
    # Both images; or, to finish one whose other image went up alone (its upload
    # broke off), only the missing one.
    before: SideIn | None = None
    after: SideIn | None = None
    before_label: str | None = Field(default=None, max_length=255)
    after_label: str | None = Field(default=None, max_length=255)


class ComparisonUploadOut(BaseModel):
    # Send each image here with one PUT, as for an ordinary upload; None: not asked for.
    before_url: str | None = None
    after_url: str | None = None


def _title(title: str) -> str:
    try:
        cleaned = _clean(title)
    except ApiError:
        raise ApiError(422, ErrorCode.COMPARISON_TITLE_INVALID) from None
    if len(cleaned) > comparisons.TITLE_MAX:
        raise ApiError(422, ErrorCode.COMPARISON_TITLE_INVALID)
    return cleaned


def _taken(documents: list[versions.Document], key: str, besides=()) -> bool:
    """A document of the folder already marked for a comparison of this title
    (`besides`: the comparison's own sides, when it is renamed): a third side
    would leave all of them unpaired."""
    for document in documents:
        found = comparisons.marked(document.named.base)
        if found is not None and found.key == key and all(document is not b for b in besides):
            return True
    return False


def _room_for(documents: list[versions.Document], key: str, wanted: set[Side]) -> bool:
    """Whether the folder can take these sides of the comparison of this title:
    nothing marked for that title yet, for both; for one, only the other side,
    alone (the first try's image that went up)."""
    marked = [m for d in documents if (m := comparisons.marked(d.named.base)) and m.key == key]
    if len(wanted) == 2:
        return not marked
    return len(marked) == 1 and marked[0].side not in wanted


@router.post(
    "/api/projects/{project_id}/stages/{position}/comparisons",
    responses=documented(401, 404, 409, 422, 503),
)
async def start_comparison(
    request: Request,
    project_id: uuid.UUID,
    position: int,
    body: ComparisonIn,
    _staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> ComparisonUploadOut:
    """ "Comparação antes e depois": both images go up, named so the page pairs
    them (`Cozinha (antes).jpg`, `Cozinha (depois).jpg`)."""
    sides = {
        side: chosen
        for side, chosen in ((Side.BEFORE, body.before), (Side.AFTER, body.after))
        if chosen is not None
    }
    if not sides:
        raise ApiError(422, ErrorCode.INVALID_REQUEST)  # the page always sends one
    for side in sides.values():
        if side.size > UPLOAD_MAX:
            raise ApiError(422, ErrorCode.FILE_TOO_LARGE)
        if side.mime_type not in INLINE_IMAGES:
            raise ApiError(422, ErrorCode.COMPARISON_NOT_IMAGE)
    title = _title(body.title)
    labels = {
        Side.BEFORE: comparisons.clean_label(body.before_label),
        Side.AFTER: comparisons.clean_label(body.after_label),
    }
    _project, stage, reader = await _stage_for_upload(
        request, db, tenant, project_id, position, body.row_version
    )
    try:
        folder = await _section(reader, stage, body.folder)
        if reader is not None and not _room_for(
            await _documents(reader, folder), comparisons.title_key(title), set(sides)
        ):
            raise ApiError(409, ErrorCode.COMPARISON_EXISTS)
    except StorageError as error:
        raise _listing_failed(error, tenant, project_id, position) from None
    names = {
        side: comparisons.base_name(title, side, labels[side], tenant.locale.value)
        + versions.parse(_clean(chosen.name)).extension.casefold()
        for side, chosen in sides.items()
    }
    maker, _root = await _folders(request, db)
    urls = {}
    for side, chosen in sides.items():
        if isinstance(maker, LocalFolders):
            urls[side] = local_upload_url(request, tenant, folder, names[side], chosen.size)
            continue
        try:
            urls[side] = await maker.start_upload(
                names[side], folder, chosen.size, chosen.mime_type, upload_origin(request, tenant)
            )
        except ConnectError as error:
            log.error(
                "comparisons: opening an upload failed for %s/%s, stage %s: %s",
                tenant.id,
                project_id,
                position,
                error.detail,
            )
            raise ApiError(503, ErrorCode.DRIVE_CONNECT_FAILED) from None
    log.info("comparisons: opened for %s/%s, stage %s", tenant.id, project_id, position)
    capture(
        request,
        "comparison_upload_started",
        {"bytes": sum(chosen.size for chosen in sides.values()), "stage_position": position},
    )
    return ComparisonUploadOut(before_url=urls.get(Side.BEFORE), after_url=urls.get(Side.AFTER))


async def _comparison_at(
    request: Request, db: AsyncSession, tenant: CurrentTenant, project: Project, key: str
):
    """The storage view, the folder's documents and the comparison whose card the
    key is (its "before" side's current version), still as the page lists it."""
    reader, item, found = await _item_at(request, db, project, key)
    try:
        documents = await _documents(reader, found["f"])
    except StorageError as error:
        raise _listing_failed(error, tenant, project.id, found.get("s")) from None
    for entry in comparisons.pair(documents, _is_image):
        if isinstance(entry, comparisons.Comparison) and entry.before.current.id == item.id:
            return reader, documents, entry, found
    raise ApiError(404, ErrorCode.FILE_NOT_FOUND)  # renamed or taken apart meanwhile: reload


def _items(comparison: comparisons.Comparison) -> list:
    return [item for side in (comparison.before, comparison.after) for _n, item in side.versions]


async def _change(request, db, tenant, project, comparison, operation, action) -> None:
    """`action(maker, item)` on every file of the comparison, once the app may
    change all of them: one made straight in Drive stops it before any changes."""
    maker, _root = await _folders(request, db)
    try:
        for item in _items(comparison):
            if not await maker.can_rename(item.id):
                raise ApiError(409, ErrorCode.COMPARISON_NOT_OURS)
        for item in _items(comparison):
            await action(maker, item)
    except ConnectError as error:
        log.error(
            "comparisons: %s failed for %s/%s: %s", operation, tenant.id, project.id, error.detail
        )
        raise ApiError(503, ErrorCode.DRIVE_CONNECT_FAILED) from None


class ComparisonEditIn(BaseModel):
    title: str = Field(max_length=255)
    before_label: str | None = Field(default=None, max_length=255)
    after_label: str | None = Field(default=None, max_length=255)


@router.post(
    "/api/pages/{slug}/comparisons/{key}/edit",
    status_code=204,
    responses=documented(401, 404, 409, 422, 503),
)
async def edit_comparison(
    request: Request,
    slug: str,
    key: str,
    body: ComparisonEditIn,
    staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> Response:
    """Its title and labels are in its files' names: each version of both sides
    is renamed, keeping its version (`Cozinha (antes - Obra) v2.jpg`)."""
    project = await _readable(db, slug, staff, request)
    await _changeable(db, project.id)
    title = _title(body.title)
    _reader, documents, comparison, _found = await _comparison_at(request, db, tenant, project, key)
    besides = (comparison.before, comparison.after)
    if _taken(documents, comparisons.title_key(title), besides):
        raise ApiError(409, ErrorCode.COMPARISON_EXISTS)
    new = {}
    for side, document, label in (
        (Side.BEFORE, comparison.before, body.before_label),
        (Side.AFTER, comparison.after, body.after_label),
    ):
        base = comparisons.base_name(
            title, side, comparisons.clean_label(label), tenant.locale.value
        )
        new.update(comparisons.renamed(document, base))
    names = {item.id: item.name for item in _items(comparison)}

    async def rename(maker, item):
        if new[item.id] != names[item.id]:
            await maker.rename(item.id, new[item.id])

    await _change(request, db, tenant, project, comparison, "renaming", rename)
    capture(request, "comparison_edited")
    return Response(status_code=204)


@router.post(
    "/api/pages/{slug}/comparisons/{key}/hide",
    status_code=204,
    responses=documented(401, 404, 409, 503),
)
async def hide_comparison(
    request: Request,
    slug: str,
    key: str,
    staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> Response:
    """Both sides, every version, stay in Drive renamed "_name" (A05)."""
    project = await _readable(db, slug, staff, request)
    await _changeable(db, project.id)
    _reader, _listed, comparison, _found = await _comparison_at(request, db, tenant, project, key)

    async def hide(maker, item):
        await maker.rename(item.id, f"_{item.name}")

    await _change(request, db, tenant, project, comparison, "hiding", hide)
    capture(request, "comparison_hidden")
    return Response(status_code=204)


class ComparisonMoveIn(BaseModel):
    row_version: int
    position: int  # the stage it goes to, from 1
    folder: str | None = Field(default=None, max_length=255)  # one of its sections, by name


@router.post(
    "/api/pages/{slug}/comparisons/{key}/move",
    status_code=204,
    responses=documented(401, 404, 409, 503),
)
async def move_comparison(
    request: Request,
    slug: str,
    key: str,
    body: ComparisonMoveIn,
    staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> Response:
    """Both sides, every version, into a stage's folder or one of its sections,
    as "Mover para…" moves a file; refused where that title is already compared."""
    project = await _readable(db, slug, staff, request)
    await _changeable(db, project.id)
    if project.row_version != body.row_version:
        raise ApiError(409, ErrorCode.PROJECT_CHANGED)  # that position may be another stage now
    stage = await db.scalar(
        select(ProjectStage).where(
            ProjectStage.project_id == project.id, ProjectStage.position == body.position
        )
    )
    if stage is None:
        raise ApiError(404, ErrorCode.PROJECT_NOT_FOUND)
    if stage.folder_id is None:
        raise ApiError(409, ErrorCode.STAGE_HAS_NO_FOLDER)
    reader, _listed, comparison, found = await _comparison_at(request, db, tenant, project, key)
    try:
        if stage.folder_id not in await _in_project(reader, project):
            raise ApiError(409, ErrorCode.STAGE_HAS_NO_FOLDER)  # moved out of the project in Drive
        target = await _section(reader, stage, body.folder)
        if target == found["f"]:
            return Response(status_code=204)  # already there
        there = await _documents(reader, target)
    except StorageError as error:
        raise _listing_failed(error, tenant, project.id, body.position) from None
    if _taken(there, comparisons.title_key(comparison.title)):
        raise ApiError(409, ErrorCode.COMPARISON_EXISTS)

    async def move(maker, item):
        await maker.move(item.id, target)

    await _change(request, db, tenant, project, comparison, "moving", move)
    capture(request, "comparison_moved")
    return Response(status_code=204)
