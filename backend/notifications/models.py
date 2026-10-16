"""Who receives a project's email updates (A32, plan section 14)."""

from __future__ import annotations

import uuid
from enum import StrEnum

from sqlalchemy import CheckConstraint, Text, UniqueConstraint, text
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
