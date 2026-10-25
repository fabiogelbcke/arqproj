"""Links that share a project's files, say with a supplier (A37, plan section 15).

A link holds the exact versions it was made with: each file by its storage
identity, found again in the project's folders on every visit. Only a hash of
its token is stored.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base, IdMixin, TimestampsMixin
from backend.db.isolation import TenantOwned
from backend.projects.models import _project_fk

LABEL_MAX = 60  # "Para quem?": a supplier's name, not a message


class ShareLink(IdMixin, TimestampsMixin, TenantOwned, Base):
    """One link to some of a project's files, made by a staff member or by the
    client (no account: `created_by` is None)."""

    __tablename__ = "share_links"
    __table_args__ = (
        _project_fk("share_links"),
        # Lets its files reference (tenant_id, id): always the same office.
        UniqueConstraint("tenant_id", "id", name="uq_share_links_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "created_by"],
            ["users.tenant_id", "users.id"],
            name="fk_share_links_creator",
        ),
        CheckConstraint(
            f"label IS NULL OR (length(btrim(label)) > 0 AND length(label) <= {LABEL_MAX})",
            name="label_length",
        ),
        CheckConstraint("downloads >= 0 AND day_bytes >= 0", name="counts_not_negative"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(index=True)
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    label: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column()
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # None: never
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # "Atualizar link": when it last moved to its files' newer versions.
    files_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    downloads: Mapped[int] = mapped_column(server_default=text("0"))
    last_download_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Bytes served on `day` (UTC), against the daily cap.
    day: Mapped[date | None] = mapped_column(Date)
    day_bytes: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))


class ShareLinkFile(IdMixin, TenantOwned, Base):
    """One file of a link: the version picked, by its storage identity."""

    __tablename__ = "share_link_files"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "link_id"],
            ["share_links.tenant_id", "share_links.id"],
            ondelete="CASCADE",
            name="fk_share_link_files_link",
        ),
        UniqueConstraint("link_id", "item_id", name="uq_share_link_files_link_id_item_id"),
    )

    link_id: Mapped[uuid.UUID] = mapped_column(index=True)
    item_id: Mapped[str] = mapped_column(Text)
    position: Mapped[int] = mapped_column()  # the order it was picked in
