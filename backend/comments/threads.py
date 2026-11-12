"""A project's comments (A49) as the page shows them: each stage's, and each
file's by its identity in storage."""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.comments.models import Author, Comment


@dataclass
class Threads:
    by_stage: dict[uuid.UUID, list[Comment]] = field(default_factory=lambda: defaultdict(list))
    by_item: dict[str, list[Comment]] = field(default_factory=lambda: defaultdict(list))

    def of_items(self, identities: list[str]) -> list[Comment]:
        """A card's: every one of its files' (its versions, a comparison's two
        sides), oldest first."""
        found = [c for identity in identities for c in self.by_item.get(identity, [])]
        return sorted(found, key=lambda c: c.created_at)


async def threads(db: AsyncSession, project_id: uuid.UUID) -> Threads:
    """Every comment not removed, oldest first."""
    found = Threads()
    for comment in await db.scalars(
        select(Comment)
        .where(Comment.project_id == project_id, Comment.removed_at.is_(None))
        .order_by(Comment.created_at, Comment.id)
    ):
        if comment.stage_id is not None:
            found.by_stage[comment.stage_id].append(comment)
        else:
            found.by_item[comment.item_id].append(comment)
    return found


async def office_spots(db: AsyncSession, project_id: uuid.UUID) -> tuple[set, set[str]]:
    """The stages and files with a comment of the office's still shown: an
    `office_commented` event about anything else was taken back since."""
    rows = (
        await db.execute(
            select(Comment.stage_id, Comment.item_id).where(
                Comment.project_id == project_id,
                Comment.author == Author.STAFF,
                Comment.removed_at.is_(None),
            )
        )
    ).all()
    return {stage for stage, _ in rows if stage}, {item for _, item in rows if item}
