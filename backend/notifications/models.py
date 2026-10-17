"""Client email updates: who receives them (A32, plan section 14), and the
client-visible changes they are made of (A28)."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Text,
    UniqueConstraint,
    func,
    text,
)
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
        # Its email is the same office's and the same project's (section 7).
        ForeignKeyConstraint(
            ["tenant_id", "project_id", "batch_id"],
            [
                "notification_batches.tenant_id",
                "notification_batches.project_id",
                "notification_batches.id",
            ],
            name="fk_project_events_batch",
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column()
    kind: Mapped[EventKind] = mapped_column(TextEnum(EventKind))
    stage_position: Mapped[int | None] = mapped_column()  # the stage it is about, from 1
    item_id: Mapped[str | None] = mapped_column(Text)  # a file's id in storage
    title: Mapped[str | None] = mapped_column(Text)  # the file's, stage's or meeting's name
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # The email it went into; None until batched (a note never is: A32).
    batch_id: Mapped[uuid.UUID | None] = mapped_column()


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


class BatchState(StrEnum):
    OPEN = "open"  # gathering changes until it is due (A12)
    # Due, and going out: frozen, retried as it is until every address has it;
    # newer changes gather in a new open batch.
    SENDING = "sending"
    SENT = "sent"
    DROPPED = "dropped"  # nothing left to tell, or nobody to tell it to


class NotificationBatch(IdMixin, TimestampsMixin, TenantOwned, Base):
    """One email's worth of a project's changes (A12): due 45 minutes after the
    last change, or 2 hours after the first, whichever comes first."""

    __tablename__ = "notification_batches"
    __table_args__ = (
        _project_fk("notification_batches"),
        enum_check("state", BatchState),
        # What its events and deliveries reference: the office and project too.
        UniqueConstraint("tenant_id", "id", name="uq_notification_batches_tenant_id_id"),
        UniqueConstraint(
            "tenant_id", "project_id", "id", name="uq_notification_batches_tenant_id_project_id_id"
        ),
        # At most one batch gathering changes per project.
        Index(
            "uq_notification_batches_open_per_project",
            "project_id",
            unique=True,
            postgresql_where=text("state = 'open'"),
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(index=True)
    state: Mapped[BatchState] = mapped_column(TextEnum(BatchState), server_default=text("'open'"))
    first_event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DeliveryStatus(StrEnum):
    PENDING = "pending"  # to go: the addresses are fixed when the batch starts sending
    SENT = "sent"
    FAILED = "failed"  # tried again on the next pass, with the same idempotency key


class NotificationDelivery(IdMixin, TimestampsMixin, TenantOwned, Base):
    """A batch's email to one address: sent once, whatever the retries. Kept by
    address, not by the recipient row, so removing an address and adding it back
    can't send the same email again."""

    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint("batch_id", "email", name="uq_notification_deliveries_batch_id_email"),
        enum_check("status", DeliveryStatus),
        # The same office's batch (section 7).
        ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["notification_batches.tenant_id", "notification_batches.id"],
            name="fk_notification_deliveries_batch",
            ondelete="CASCADE",
        ),
    )

    batch_id: Mapped[uuid.UUID] = mapped_column(index=True)
    email: Mapped[str] = mapped_column(Text)
    status: Mapped[DeliveryStatus] = mapped_column(TextEnum(DeliveryStatus))
    provider_id: Mapped[str | None] = mapped_column(Text)  # Resend's id for the email
    attempts: Mapped[int] = mapped_column(server_default=text("0"))
