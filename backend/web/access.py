"""Route dependencies for who may change what, so a route declares them rather
than repeating the check in its body (`backend/tests/test_route_rules.py` checks
every route has the ones it needs).

- `require_owner`: only the office's owners (A36); the CSRF check comes with it.
- `changeable_project`: the project in the path, 404 for none (or another
  office's), 409 `project_archived` while archived: viewable, not changed (plan
  section 22). Its own CSRF check runs first, so nobody signed out learns
  whether a project exists.
"""

from __future__ import annotations

import uuid

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.engine import get_tenant_session
from backend.identity.models import Role
from backend.projects.enums import ProjectStatus
from backend.projects.models import Project
from backend.web.auth import CurrentStaff, require_csrf
from backend.web.errors import ApiError, ErrorCode


def refuse_unless_owner(staff: CurrentStaff) -> None:
    """For the one change only owners may make inside a route anyone may use
    (a proposal saved with "update the office's details"); routes use `require_owner`."""
    if staff.role is not Role.OWNER:
        raise ApiError(403, ErrorCode.OWNER_ONLY)


async def require_owner(staff: CurrentStaff = Depends(require_csrf)) -> CurrentStaff:
    """A state-changing request from one of the office's owners: 403 for a member."""
    refuse_unless_owner(staff)
    return staff


async def changeable(db: AsyncSession, project_id: uuid.UUID, lock: bool = False) -> Project:
    """The project, if it may be changed; `lock` holds its row until the transaction ends."""
    query = select(Project).where(Project.id == project_id, Project.deleted_at.is_(None))
    project = await db.scalar(query.with_for_update() if lock else query)
    if project is None:
        raise ApiError(404, ErrorCode.PROJECT_NOT_FOUND)
    if project.status is ProjectStatus.ARCHIVED:
        raise ApiError(409, ErrorCode.PROJECT_ARCHIVED)
    return project


async def changeable_project(
    project_id: uuid.UUID,
    _staff: CurrentStaff = Depends(require_csrf),
    db: AsyncSession = Depends(get_tenant_session),
) -> Project:
    """For a route that changes `/api/projects/{project_id}/…`."""
    return await changeable(db, project_id)


async def locked_changeable_project(
    project_id: uuid.UUID,
    _staff: CurrentStaff = Depends(require_csrf),
    db: AsyncSession = Depends(get_tenant_session),
) -> Project:
    """`changeable_project`, its row locked until the request's transaction ends:
    for a change that must not race another (two saves numbering a version)."""
    return await changeable(db, project_id, lock=True)
