"""Client email updates: who receives them (A32, plan section 14), and the
client-visible changes they are made of (A28)."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, Index, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base, IdMixin, TimestampsMixin
from backend.db.isolation import TenantOwned
from backend.db.types import TextEnum, enum_check
from backend.projects.models import _project_fk

RECIPIENTS_MAX = 20  # a family or a company's few contacts, not a mailing list
EMAIL_MAX = 254


class RecipientStatus(StrEnum):
    SUBSCRIBED = "subscribed"
    # The client followed the email's link: never written to again, and staff
    # can't undo it by removing and adding the address (section 14).
    UNSUBSCRIBED = "unsubscribed"


class ProjectRecipient(IdMixin, TimestampsMixin, TenantOwned, Base):
    """An address staff entered in the Projeto dialog for this project's updates."""

    __tablename__ = "project_recipients"
    __table_args__ = (
        _project_fk("project_recipients"),
        UniqueConstraint("project_id", "email", name="uq_project_recipients_project_id_email"),
        enum_check("status", RecipientStatus),
        CheckConstraint(
            f"email = lower(email) AND email LIKE '%_@_%.__%' AND length(email) <= {EMAIL_MAX}",
            name="email_format",
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(index=True)
    email: Mapped[str] = mapped_column(Text)
    status: Mapped[RecipientStatus] = mapped_column(
        TextEnum(RecipientStatus), server_default=text("'subscribed'")
    )


class EventKind(StrEnum):
    """What a client can notice on the page (A28). All but a note email (A32)."""

    FILE_PUBLISHED = "file_published"  # found by the scan in a stage's folder
    STAGE_ADVANCED = "stage_advanced"
    PROJECT_COMPLETED = "project_completed"
    MEETING_SCHEDULED = "meeting_scheduled"
    MEETING_CHANGED = "meeting_changed"
    MEETING_CLEARED = "meeting_cleared"
    NOTE_CHANGED = "note_changed"


class ProjectEvent(IdMixin, TenantOwned, Base):
    """One client-visible change, recorded once (A28): emails, "Atualizado" and the
    updates panel read these. What it names is copied in, as it was then."""

    __tablename__ = "project_events"
    __table_args__ = (
        _project_fk("project_events"),
        enum_check("kind", EventKind),
        Index("ix_project_events_project_id_occurred_at", "project_id", "occurred_at"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column()
    kind: Mapped[EventKind] = mapped_column(TextEnum(EventKind))
    stage_position: Mapped[int | None] = mapped_column()  # the stage it is about, from 1
    item_id: Mapped[str | None] = mapped_column(Text)  # a file's id in storage
    title: Mapped[str | None] = mapped_column(Text)  # the file's, stage's or meeting's name
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ProjectFileSeen(IdMixin, TenantOwned, Base):
    """A file the project's page has shown: the scan compares each listing with
    these, so a file is "new" once, the first time it shows (A10)."""

    __tablename__ = "project_files_seen"
    __table_args__ = (
        _project_fk("project_files_seen"),
        UniqueConstraint("project_id", "item_id", name="uq_project_files_seen_project_id_item_id"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column()
    item_id: Mapped[str] = mapped_column(Text)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
