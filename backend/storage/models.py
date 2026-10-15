"""Which file store each office uses (one per office for now).

The fuller connection model (the office's OAuth writer, separate read and write
health) arrives with the Drive connection screen in slice 3.
"""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import CheckConstraint, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base, IdMixin, TimestampsMixin
from backend.db.isolation import TenantOwned
from backend.db.types import TextEnum, enum_check


class StorageKind(StrEnum):
    GOOGLE = "google"  # Google Drive (staging, production)
    FOLDER = "folder"  # a folder on this machine (local development only)


class StorageConnection(IdMixin, TimestampsMixin, TenantOwned, Base):
    __tablename__ = "storage_connections"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_storage_connections_tenant_id"),
        enum_check("kind", StorageKind),
        CheckConstraint(
            "kind <> 'google' OR reader_identity IS NOT NULL", name="google_has_reader"
        ),
    )

    kind: Mapped[StorageKind] = mapped_column(TextEnum(StorageKind))
    # The office's root folder: a Drive folder id, or a path under the local root.
    root_id: Mapped[str] = mapped_column(Text, server_default=text("''"))
    # The Google identity the folder is shared with for reading (plan section 9).
    reader_identity: Mapped[str | None] = mapped_column(Text)
