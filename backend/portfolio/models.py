"""The office's portfolio: the page its own address shows at `/` once published,
behind the `portfolio` feature (A40).

One `portfolios` row per office holds the page's settings. Each work shown is a
`portfolio_entries` row, optionally drawn from one of the office's projects, with
its photos and videos in order. Both are kept in the office's storage (a
`_portfolio` folder in its root): photos as copies, so a project's files can
change or go without the portfolio changing; videos as sent from the computer.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base, CreatedAtMixin, IdMixin, TimestampsMixin
from backend.db.isolation import TenantOwned
from backend.db.types import TextEnum, enum_check
from backend.projects.enums import CoverType, DetailType
from backend.projects.models import value_matches_type

INTRO_MAX = 600
TITLE_MAX = 80
PLACE_MAX = 80
DESCRIPTION_MAX = 2000
ENTRIES_MAX = 60
PHOTOS_MAX = 30
YEAR_MIN = 1900
YEAR_MAX = 2100
CREDITS_MAX = 120
DETAILS_MAX = 20
LABEL_MAX = 40  # an own label, one line beside its value like a built-in's
LINK_MAX = 300
VIDEOS_MAX = 6
VIDEO_MAX_BYTES = 200 * 1024 * 1024


class WorkStatus(StrEnum):
    """Where a work stands, as the public page says it."""

    COMPLETED = "completed"
    IN_PROGRESS = "in_progress"


class VideoType(StrEnum):
    """Videos every browser plays: MP4 (H.264, what phones and Instagram export)
    and WebM."""

    MP4 = "video/mp4"
    WEBM = "video/webm"


class SocialNetwork(StrEnum):
    """The networks the page links to, in the footer's order."""

    INSTAGRAM = "instagram"
    LINKEDIN = "linkedin"
    PINTEREST = "pinterest"
    YOUTUBE = "youtube"
    VIMEO = "vimeo"
    BEHANCE = "behance"
    FACEBOOK = "facebook"
    TIKTOK = "tiktok"


class PortfolioFormat(StrEnum):
    """How the public page lays the works out. GALLERY: one landscape cover per
    work, a carousel and a work's page opening on its cover, as architecture
    sites do. MOSAIC: every image in its own shape, square or upright, as the
    networks show them: for an office whose material is what it made for its
    posts, stories and reels."""

    GALLERY = "gallery"
    MOSAIC = "mosaic"


class Portfolio(IdMixin, TimestampsMixin, TenantOwned, Base):
    """The page's settings: whether the office's address shows it, its format,
    its text and the office's profiles on social networks."""

    __tablename__ = "portfolios"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_portfolios_tenant_id"),
        enum_check("format", PortfolioFormat),
        CheckConstraint(f"length(intro) <= {INTRO_MAX}", name="intro_length"),
        CheckConstraint("jsonb_typeof(links) = 'object'", name="links_object"),
    )

    published: Mapped[bool] = mapped_column(default=False)
    format: Mapped[PortfolioFormat] = mapped_column(
        TextEnum(PortfolioFormat), default=PortfolioFormat.GALLERY, server_default=text("'gallery'")
    )
    intro: Mapped[str] = mapped_column(Text, default="")
    # {network: profile address} (SocialNetwork), checked by backend/portfolio/links.py.
    links: Mapped[dict[str, str]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
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
        enum_check("status", WorkStatus),
        CheckConstraint(f"length(credits) <= {CREDITS_MAX}", name="credits_length"),
    )

    position: Mapped[int] = mapped_column()
    title: Mapped[str] = mapped_column(Text)
    place: Mapped[str] = mapped_column(Text, default="")
    year: Mapped[int | None] = mapped_column()
    description: Mapped[str] = mapped_column(Text, default="")
    # Architecture, interiors, ...: the public page's menu groups works by it.
    # From the project when drawn from one; None: shown only under "all".
    project_type: Mapped[str | None] = mapped_column(
        Text, ForeignKey("project_types.key", name="fk_portfolio_entries_project_type")
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    status: Mapped[WorkStatus | None] = mapped_column(TextEnum(WorkStatus))
    # Who took the photos ("Fotos: ..."), as architecture sites credit them.
    credits: Mapped[str] = mapped_column(Text, default="", server_default=text("''"))


class PortfolioDetail(IdMixin, TenantOwned, Base):
    """A line of a work's sheet, in order: one of the built-in details a project
    has (`key`, typed and labelled as the project page's), or one with a label
    of the office's own (`label`, text only): "Fotografia", "Construtora"...
    A work drawn from a project starts with the project's, except its client."""

    __tablename__ = "portfolio_details"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "entry_id"],
            ["portfolio_entries.tenant_id", "portfolio_entries.id"],
            name="fk_portfolio_details_entry",
            ondelete="CASCADE",
        ),
        # A built-in row's value type is its detail type's (key, value_type).
        ForeignKeyConstraint(
            ["key", "value_type"],
            ["detail_types.key", "detail_types.value_type"],
            name="fk_portfolio_details_detail_type",
        ),
        UniqueConstraint("entry_id", "key", name="uq_portfolio_details_entry_id_key"),
        UniqueConstraint(
            "entry_id",
            "position",
            name="uq_portfolio_details_entry_id_position",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint("position >= 1", name="position_positive"),
        # Built-in (a key, no label) or the office's own (a label, no key, text).
        CheckConstraint(
            "(key IS NOT NULL AND label IS NULL) "
            "OR (key IS NULL AND label IS NOT NULL AND value_type = 'text')",
            name="built_in_or_own",
        ),
        CheckConstraint(
            f"label IS NULL OR length(btrim(label)) BETWEEN 1 AND {LABEL_MAX}",
            name="label_length",
        ),
        enum_check("value_type", DetailType),
        CheckConstraint(value_matches_type(), name="value_matches_type"),
        CheckConstraint(
            "value_text IS NULL OR length(btrim(value_text)) > 0", name="text_not_blank"
        ),
        CheckConstraint("value_number IS NULL OR value_number >= 0", name="number_not_negative"),
    )

    entry_id: Mapped[uuid.UUID] = mapped_column(index=True)
    position: Mapped[int] = mapped_column()
    key: Mapped[str | None] = mapped_column(Text)
    label: Mapped[str | None] = mapped_column(Text)
    value_type: Mapped[DetailType] = mapped_column(TextEnum(DetailType))
    value_text: Mapped[str | None] = mapped_column(Text)
    value_number: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    value_date: Mapped[date | None] = mapped_column(Date)


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
        CheckConstraint("width > 0 AND height > 0", name="size_positive"),
    )

    entry_id: Mapped[uuid.UUID] = mapped_column(index=True)
    position: Mapped[int] = mapped_column()
    # In the office's storage: a Drive file id, or a path in the local folder.
    file_id: Mapped[str] = mapped_column(Text)
    image_type: Mapped[CoverType] = mapped_column(TextEnum(CoverType))
    # Pixels, read from the file when added, so the page lays the photo out at
    # its shape before it loads; None when the file couldn't be read.
    width: Mapped[int | None] = mapped_column()
    height: Mapped[int | None] = mapped_column()


class PortfolioVideo(IdMixin, CreatedAtMixin, TenantOwned, Base):
    """One video of an entry, in its order, shown above its photos. The browser
    sends the file straight to the office's storage (A31) and a frame of it, the
    poster shown until it plays."""

    __tablename__ = "portfolio_videos"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "entry_id"],
            ["portfolio_entries.tenant_id", "portfolio_entries.id"],
            name="fk_portfolio_videos_entry",
            ondelete="CASCADE",
        ),
        CheckConstraint("position >= 1", name="position_positive"),
        enum_check("video_type", VideoType),
        enum_check("poster_type", CoverType),
        CheckConstraint("width > 0 AND height > 0", name="size_positive"),
    )

    entry_id: Mapped[uuid.UUID] = mapped_column(index=True)
    position: Mapped[int] = mapped_column()
    # In the office's storage, as photos' are.
    file_id: Mapped[str] = mapped_column(Text)
    video_type: Mapped[VideoType] = mapped_column(TextEnum(VideoType))
    poster_file_id: Mapped[str] = mapped_column(Text)
    poster_type: Mapped[CoverType] = mapped_column(TextEnum(CoverType))
    # The poster's pixels, the video's own shape (a 9:16 story is upright).
    width: Mapped[int | None] = mapped_column()
    height: Mapped[int | None] = mapped_column()
