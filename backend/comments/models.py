"""Comments on a project's files and stages, by clients and staff (A49)."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base, CreatedAtMixin, IdMixin
from backend.db.isolation import TenantOwned
from backend.db.types import TextEnum, enum_check
from backend.projects.models import _project_fk

BODY_MAX = 2000
NAME_MAX = 60  # a client's name, as they type it


class Author(StrEnum):
    CLIENT = "client"  # signed with a typed name: clients have no accounts (A06)
    STAFF = "staff"  # one of the office's accounts


class Comment(IdMixin, CreatedAtMixin, TenantOwned, Base):
    """One comment, on a stage or on a file. A file's is kept by its identity in
    storage, so it follows the document through versions, renames and moves; a
    stage's goes with its stage."""

    __tablename__ = "comments"
    __table_args__ = (
        _project_fk("comments"),
        ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            ondelete="SET NULL (user_id)",
            name="fk_comments_user",
        ),
        enum_check("author", Author),
        CheckConstraint("(stage_id IS NULL) <> (item_id IS NULL)", name="stage_or_file"),
        CheckConstraint(f"length(btrim(body)) BETWEEN 1 AND {BODY_MAX}", name="body_length"),
        CheckConstraint(
            f"length(btrim(author_name)) BETWEEN 1 AND {NAME_MAX}", name="author_name_length"
        ),
        # A staff comment names its account; the account may be removed later.
        CheckConstraint("author = 'staff' OR user_id IS NULL", name="client_has_no_account"),
        Index("ix_comments_project_id_created_at", "project_id", "created_at"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column()
    # A stage's conversation: gone with the stage.
    stage_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_stages.id", ondelete="CASCADE", name="fk_comments_stage"), index=True
    )
    item_id: Mapped[str | None] = mapped_column(Text)  # a file's identity in storage
    item_name: Mapped[str | None] = mapped_column(Text)  # its name then, for staff's email
    author: Mapped[Author] = mapped_column(TextEnum(Author))
    user_id: Mapped[uuid.UUID | None] = mapped_column()
    # As it was when written: a client's typed name, or the staff account's name.
    author_name: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # A client's comment: when the office's staff were emailed about it.
    staff_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
