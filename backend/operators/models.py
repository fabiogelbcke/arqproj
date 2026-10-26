"""Platform audit history, retained after a tenant is deleted. Operator-only."""

import uuid

from sqlalchemy import Text
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
