"""Which file store each office uses (one per office for now).

The fuller connection model (the office's OAuth writer, separate read and write
health) arrives with the Drive connection screen in slice 3.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, Index, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base, IdMixin, TimestampsMixin
from backend.db.isolation import TenantOwned
from backend.db.types import TextEnum, enum_check


class WriterStatus(StrEnum):
    """The office's own grant, used to create folders and upload."""

    NONE = "none"  # never connected, or disconnected
    CONNECTED = "connected"
    EXPIRED = "expired"  # Google refused the stored grant: reconnect


class ReaderStatus(StrEnum):
    """The reader identity's access to the office's folder (pages, downloads)."""

    UNKNOWN = "unknown"
    OK = "ok"
    NO_ACCESS = "no_access"


class StorageKind(StrEnum):
    GOOGLE = "google"  # Google Drive (staging, production)
    FOLDER = "folder"  # a folder on this machine (local development only)


class StorageConnection(IdMixin, TimestampsMixin, TenantOwned, Base):
    __tablename__ = "storage_connections"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_storage_connections_tenant_id"),
        # One Drive folder never serves two offices: isolation of the rows would
        # not isolate a shared tree (plan section 7). Unique across all offices,
        # which row-level security does not narrow. Nested roots (one office's
        # root inside another's) need Drive's folder ancestry, so the connection
        # screen checks those when an office connects (slice 3).
        Index(
            "uq_storage_connections_google_root",
            "root_id",
            unique=True,
            postgresql_where=text("kind = 'google'"),
        ),
        enum_check("kind", StorageKind),
        CheckConstraint(
            "kind <> 'google' OR reader_identity IS NOT NULL", name="google_has_reader"
        ),
        CheckConstraint("kind <> 'google' OR root_id <> ''", name="google_has_root"),
        enum_check("writer_status", WriterStatus),
        enum_check("reader_status", ReaderStatus),
        CheckConstraint(
            "writer_status <> 'connected' OR writer_token IS NOT NULL", name="connected_has_token"
        ),
    )

    kind: Mapped[StorageKind] = mapped_column(TextEnum(StorageKind))
    # The office's root folder: a Drive folder id, or a path under the local root.
    root_id: Mapped[str] = mapped_column(Text, server_default=text("''"))
    # The Google identity the folder is shared with for reading (plan section 9).
    reader_identity: Mapped[str | None] = mapped_column(Text)
    # The Google account that connected, shown in the painel.
    account_email: Mapped[str | None] = mapped_column(Text)
    # The office's refresh token, encrypted (backend.security.keys); never logged.
    writer_token: Mapped[str | None] = mapped_column(Text)
    writer_status: Mapped[WriterStatus] = mapped_column(
        TextEnum(WriterStatus), server_default=text("'none'")
    )
    reader_status: Mapped[ReaderStatus] = mapped_column(
        TextEnum(ReaderStatus), server_default=text("'unknown'")
    )
    connected_by: Mapped[uuid.UUID | None] = mapped_column()
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def disconnected(self) -> bool:
        """The office chose "Desconectar" and its folder is still on record: its
        clients' pages are offline and the painel hides its projects until Drive
        is back (Fabio, 25 Oct 2026). An expired grant is not this: its pages
        keep reading through the reader identity."""
        return (
            self.kind is StorageKind.GOOGLE
            and self.writer_status is WriterStatus.NONE
            and bool(self.root_id)
        )
