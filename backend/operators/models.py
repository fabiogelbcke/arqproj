"""Platform records outside any office, operator-only: the audit history, kept
after a tenant is deleted, and the links that let someone create an office."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base, CreatedAtMixin, IdMixin


class OperatorAuditEvent(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "operator_audit_events"

    actor: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text)
    # Deliberately no FK: deleting a tenant must not erase its audit history.
    target_tenant_id: Mapped[uuid.UUID] = mapped_column(index=True)
    target_slug: Mapped[str] = mapped_column(Text)
    request_id: Mapped[str] = mapped_column(Text)


class OfficeSignupLink(IdMixin, CreatedAtMixin, Base):
    """A one-time link an operator sends so its holder creates their own office
    (name and address) on Unio's address, then becomes its owner through the
    office's owner link. Only a hash of the token is stored."""

    __tablename__ = "office_signup_links"

    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    created_by: Mapped[str] = mapped_column(Text)  # the operator's email
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The office it created. No FK, like the audit's: deleting the office keeps this.
    created_tenant_id: Mapped[uuid.UUID | None]
