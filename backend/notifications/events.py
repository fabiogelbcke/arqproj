"""Recording client-visible changes (A28) as they happen."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.notifications.models import EventKind, ProjectEvent
from backend.projects.enums import ProjectStatus
from backend.projects.models import Project

# A draft has no client yet: its changes are nobody's news (section 10).
CLIENT_VISIBLE = frozenset({ProjectStatus.ACTIVE, ProjectStatus.COMPLETED})


def record(
    db: AsyncSession,
    project: Project,
    kind: EventKind,
    *,
    stage_position: int | None = None,
    item_id: str | None = None,
    title: str | None = None,
) -> None:
    """Add the change to the session, saved with the change itself."""
    if project.status not in CLIENT_VISIBLE:
        return
    db.add(
        ProjectEvent(
            project_id=project.id,
            kind=kind,
            stage_position=stage_position,
            item_id=item_id,
            title=title,
        )
    )
