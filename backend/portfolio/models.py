"""The office's portfolio: the page its own address shows at `/` once published,
behind the `portfolio` feature (A40).

One `portfolios` row per office holds the page's settings. Each work shown is a
`portfolio_entries` row, optionally drawn from one of the office's projects, with
its photos in order. Photos are copies kept in the office's storage (a
`_portfolio` folder in its root), so a project's files can change or go without
the portfolio changing.
"""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base, CreatedAtMixin, IdMixin, TimestampsMixin
from backend.db.isolation import TenantOwned
from backend.db.types import TextEnum, enum_check
from backend.projects.enums import CoverType

INTRO_MAX = 600
TITLE_MAX = 80
PLACE_MAX = 80
DESCRIPTION_MAX = 2000
ENTRIES_MAX = 60
PHOTOS_MAX = 30
YEAR_MIN = 1900
YEAR_MAX = 2100


class Portfolio(IdMixin, TimestampsMixin, TenantOwned, Base):
    """The page's settings: whether the office's address shows it, and its text."""

    __tablename__ = "portfolios"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_portfolios_tenant_id"),
        CheckConstraint(f"length(intro) <= {INTRO_MAX}", name="intro_length"),
    )

    published: Mapped[bool] = mapped_column(default=False)
    intro: Mapped[str] = mapped_column(Text, default="")
    # The `_portfolio` folder holding the photos, inside the office's root folder.
    folder_id: Mapped[str | None] = mapped_column(Text)


class PortfolioEntry(IdMixin, TimestampsMixin, TenantOwned, Base):
    """A work the portfolio shows. `project_id`: the project it was drawn from,
    for staff only; the public page never links to a project's page."""

    __tablename__ = "portfolio_entries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.id"],
            name="fk_portfolio_entries_project",
        ),
        # Lets photos reference (tenant_id, id): always the same office.
        UniqueConstraint("tenant_id", "id", name="uq_portfolio_entries_tenant_id_id"),
        CheckConstraint("position >= 1", name="position_positive"),
        CheckConstraint(f"length(btrim(title)) BETWEEN 1 AND {TITLE_MAX}", name="title_length"),
        CheckConstraint(f"length(place) <= {PLACE_MAX}", name="place_length"),
        CheckConstraint(f"length(description) <= {DESCRIPTION_MAX}", name="description_length"),
        CheckConstraint(f"year BETWEEN {YEAR_MIN} AND {YEAR_MAX}", name="year_range"),
    )

    position: Mapped[int] = mapped_column()
    title: Mapped[str] = mapped_column(Text)
    place: Mapped[str] = mapped_column(Text, default="")
    year: Mapped[int | None] = mapped_column()
    description: Mapped[str] = mapped_column(Text, default="")
    project_id: Mapped[uuid.UUID | None] = mapped_column(index=True)


class PortfolioPhoto(IdMixin, CreatedAtMixin, TenantOwned, Base):
    """One photo of an entry, in its order; the first is the entry's cover."""

    __tablename__ = "portfolio_photos"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "entry_id"],
            ["portfolio_entries.tenant_id", "portfolio_entries.id"],
            name="fk_portfolio_photos_entry",
            ondelete="CASCADE",
        ),
        CheckConstraint("position >= 1", name="position_positive"),
        enum_check("image_type", CoverType),
    )

    entry_id: Mapped[uuid.UUID] = mapped_column(index=True)
    position: Mapped[int] = mapped_column()
    # In the office's storage: a Drive file id, or a path in the local folder.
    file_id: Mapped[str] = mapped_column(Text)
    image_type: Mapped[CoverType] = mapped_column(TextEnum(CoverType))
