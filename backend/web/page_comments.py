"""Comments on a project's files and stages (A49).

    POST   /api/pages/{slug}/comments        a comment, on a stage or a file
    DELETE /api/pages/{slug}/comments/{id}   staff remove one

Anyone who can open the page may comment: a client signs with the name they
type (clients have no accounts, A06), staff with their account's name. The
page lists them with the files (`page_files`), so a hidden file's go with it.
A device may post a few a minute. A staff comment is client news (A28): it
reaches the update email and the updates panel. A client's emails the office's
staff from the maintenance pass (`backend/comments/alerts.py`).
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.analytics import capture, capture_visit
from backend.comments.models import BODY_MAX, NAME_MAX, Author, Comment
from backend.db.engine import get_tenant_session
from backend.documents.versions import shown_name
from backend.notifications.events import record
from backend.notifications.models import EventKind
from backend.projects.enums import ProjectStatus
from backend.projects.models import Project, ProjectStage
from backend.tenancy.models import Feature
from backend.tenancy.resolve import CurrentTenant, current_tenant
from backend.web import attempts
from backend.web.auth import CurrentStaff, _check_csrf, optional_staff, require_csrf
from backend.web.errors import ApiError, ErrorCode, documented
from backend.web.page_files import CommentOut, _item_at, comment_out
from backend.web.pages import _readable


def _switched_on(tenant: CurrentTenant = Depends(current_tenant)) -> None:
    """Comments are a feature switched on per office (A40, A49)."""
    if not tenant.has(Feature.COMMENTS):
        raise ApiError(409, ErrorCode.FEATURE_OFF)


router = APIRouter(dependencies=[Depends(_switched_on)])

# A client's device: this many comments a minute at most. Kept in this server's
# memory, as the page's password tries are (attempts): proportional to the risk.
PER_MINUTE = 6
_posted: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def _admit(project_id: uuid.UUID, who: str, now: float | None = None) -> bool:
    now = time.monotonic() if now is None else now
    times = _posted[(str(project_id), who)]
    while times and now - times[0] >= 60:
        times.popleft()
    if len(times) >= PER_MINUTE:
        return False
    times.append(now)
    return True


class CommentIn(BaseModel):
    body: str = Field(max_length=BODY_MAX)
    # Where: a file's key, as the page listed it, or a stage's place (from 1).
    key: str | None = Field(default=None, max_length=2000)
    position: int | None = Field(default=None, ge=1)
    name: str | None = Field(default=None, max_length=NAME_MAX)  # a client's; staff's is theirs


@router.post("/api/pages/{slug}/comments", responses=documented(403, 404, 409, 422, 429))
async def add_comment(
    slug: str,
    body: CommentIn,
    request: Request,
    staff: CurrentStaff | None = Depends(optional_staff),
    db: AsyncSession = Depends(get_tenant_session),
) -> CommentOut:
    if staff is not None:
        _check_csrf(request, staff)  # signed in, a change made as them
    project = await _readable(db, slug, staff, request)  # a locked page asks for its password
    if project.status is ProjectStatus.ARCHIVED:
        raise ApiError(409, ErrorCode.PROJECT_ARCHIVED)
    text = body.body.strip()
    name = (body.name or "").strip()
    if not text or (staff is None and not name) or (body.key is None) == (body.position is None):
        raise ApiError(422, ErrorCode.INVALID_COMMENT)
    if staff is None and not _admit(project.id, attempts.device(request)):
        raise ApiError(429, ErrorCode.TOO_MANY_COMMENTS)
    comment = Comment(
        project_id=project.id,
        body=text,
        author=Author.CLIENT if staff is None else Author.STAFF,
        user_id=staff.user_id if staff else None,
        author_name=name if staff is None else staff.name,
    )
    if body.key is not None:
        # A file this page listed, still there: kept by its identity, so the
        # comment follows the document through versions, renames and moves.
        _storage, item, found = await _item_at(request, db, project, body.key)
        comment.item_id, comment.item_name = item.identity, shown_name(item)
        position, stage_id = found["s"], None
    else:
        stage_id = await db.scalar(
            select(ProjectStage.id).where(
                ProjectStage.project_id == project.id, ProjectStage.position == body.position
            )
        )
        if stage_id is None:
            raise ApiError(404, ErrorCode.INVALID_STAGE)
        comment.stage_id, position = stage_id, body.position
    db.add(comment)
    if staff is not None:
        record(
            db,
            project,
            EventKind.OFFICE_COMMENTED,
            stage_position=position,
            stage_id=stage_id,
            item_id=comment.item_id,
            title=comment.item_name,
        )
        # "Atualizado" (A28), as a new file does (the maintenance scan).
        now = datetime.now(UTC)
        touched = update(Project).where(Project.id == project.id)
        await db.execute(touched.values(last_activity_at=now))
    await db.flush()
    await db.refresh(comment)
    shown = comment_out(comment)
    await db.commit()
    on = "file" if body.key is not None else "stage"
    if staff is None:
        capture_visit(request, project.tenant_id, "client_commented", {"on": on})
    else:
        capture(request, "comment_posted", {"on": on})
    return shown


@router.delete(
    "/api/pages/{slug}/comments/{comment_id}", status_code=204, responses=documented(403, 404)
)
async def remove_comment(
    slug: str,
    comment_id: uuid.UUID,
    request: Request,
    staff: CurrentStaff = Depends(require_csrf),
    db: AsyncSession = Depends(get_tenant_session),
) -> None:
    """Any comment, by any of the office's staff: spam, or a mistake."""
    project = await _readable(db, slug, staff, request)
    comment = await db.scalar(
        select(Comment).where(
            Comment.id == comment_id,
            Comment.project_id == project.id,
            Comment.removed_at.is_(None),
        )
    )
    if comment is None:
        raise ApiError(404, ErrorCode.COMMENT_NOT_FOUND)
    comment.removed_at = datetime.now(UTC)
    await db.commit()
    capture(request, "comment_removed", {"author": comment.author.value})
