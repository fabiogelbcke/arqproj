"""Project tables. All are tenant tables under `tenant_isolation`; children point
at their project by (tenant_id, project_id), so a row can never join another
office's project. The app only reads them for now (editing: slice 3).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base, IdMixin, TimestampsMixin
from backend.db.isolation import TenantOwned
from backend.db.types import TextEnum, enum_check
from backend.projects.enums import (
    DETAIL_TYPES,
    RESERVED_SLUGS,
    AccessMode,
    BuiltinStage,
    DetailKey,
    DetailType,
    ProjectStatus,
    ProjectType,
    StageTemplate,
)

CLIENT_NAME_MAX = 48
MEETING_TITLE_MAX = 40
MEETING_LOCATION_MAX = 60


def _project_fk(table: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["tenant_id", "project_id"],
        ["projects.tenant_id", "projects.id"],
        ondelete="CASCADE",
        name=f"fk_{table}_project",
    )


class Project(IdMixin, TimestampsMixin, TenantOwned, Base):
    __tablename__ = "projects"
    __table_args__ = (
        # Lets children reference (tenant_id, id): always the same office.
        UniqueConstraint("tenant_id", "id", name="uq_projects_tenant_id_id"),
        CheckConstraint("length(btrim(name)) > 0", name="name_not_blank"),
        CheckConstraint(
            f"length(btrim(client_name)) BETWEEN 1 AND {CLIENT_NAME_MAX}", name="client_name_length"
        ),
        enum_check("status", ProjectStatus),
        enum_check("access_mode", AccessMode),
        enum_check("project_type", ProjectType),
        enum_check("stage_template", StageTemplate),
        # A password-protected project always has a password.
        CheckConstraint(
            "access_mode <> 'password' OR password_hash IS NOT NULL", name="password_set"
        ),
        CheckConstraint(
            "current_position IS NULL OR current_position >= 1", name="position_positive"
        ),
    )

    name: Mapped[str] = mapped_column(Text)
    client_name: Mapped[str] = mapped_column(Text)
    project_type: Mapped[ProjectType] = mapped_column(TextEnum(ProjectType))
    stage_template: Mapped[StageTemplate] = mapped_column(TextEnum(StageTemplate))
    description: Mapped[str] = mapped_column(Text, server_default=text("''"))
    status: Mapped[ProjectStatus] = mapped_column(
        TextEnum(ProjectStatus), server_default=text("'draft'")
    )
    access_mode: Mapped[AccessMode] = mapped_column(
        TextEnum(AccessMode), server_default=text("'public'")
    )
    password_hash: Mapped[str | None] = mapped_column(Text)
    # Changing the password or access mode bumps it, ending earlier unlocks.
    access_version: Mapped[int] = mapped_column(server_default=text("1"))
    # Position of the current stage; None before the first stage starts.
    current_position: Mapped[int | None] = mapped_column()
    # Last change a client can see (A28); orders the painel's "last updated".
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Optimistic locking for simultaneous edits (plan section 7).
    row_version: Mapped[int] = mapped_column(server_default=text("1"))
    # Soft deletion: the project and its slugs stay, so old links never reach
    # another project (A29).
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProjectSlug(IdMixin, TenantOwned, Base):
    """Every address a project has had; exactly one is current. One namespace per
    office, so a used slug can never be given to another project (A29)."""

    __tablename__ = "project_slugs"
    __table_args__ = (
        _project_fk("project_slugs"),
        UniqueConstraint("tenant_id", "slug", name="uq_project_slugs_tenant_id_slug"),
        Index(
            "uq_project_slugs_one_current",
            "project_id",
            unique=True,
            postgresql_where=text("is_current"),
        ),
        CheckConstraint(r"slug ~ '^[a-z0-9]([a-z0-9-]*[a-z0-9])?$'", name="slug_format"),
        CheckConstraint(
            "slug NOT IN (" + ", ".join(f"'{s}'" for s in RESERVED_SLUGS) + ")",
            name="slug_not_reserved",
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(index=True)
    slug: Mapped[str] = mapped_column(Text)
    is_current: Mapped[bool] = mapped_column(server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class ProjectStage(IdMixin, TimestampsMixin, TenantOwned, Base):
    """A stage: either built in (title and explanations translated) or written by
    the office (shown as typed)."""

    __tablename__ = "project_stages"
    __table_args__ = (
        _project_fk("project_stages"),
        # Deferred, so reordering can swap positions inside one transaction.
        UniqueConstraint(
            "project_id",
            "position",
            name="uq_project_stages_project_id_position",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint("position >= 1", name="position_positive"),
        enum_check("builtin_key", BuiltinStage),
        CheckConstraint("(builtin_key IS NULL) = (title IS NOT NULL)", name="builtin_or_custom"),
        CheckConstraint(
            "builtin_key IS NULL OR (about IS NULL AND deliverables IS NULL)",
            name="builtin_texts_translated",
        ),
        CheckConstraint("title IS NULL OR length(btrim(title)) > 0", name="title_not_blank"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(index=True)
    position: Mapped[int] = mapped_column()
    builtin_key: Mapped[BuiltinStage | None] = mapped_column(TextEnum(BuiltinStage))
    title: Mapped[str | None] = mapped_column(Text)
    about: Mapped[str | None] = mapped_column(Text)  # what happens in this stage
    deliverables: Mapped[str | None] = mapped_column(Text)  # what the client receives
    notes: Mapped[str] = mapped_column(Text, server_default=text("''"))
    notes_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


_VALUE_COLUMNS = {
    DetailType.TEXT: "value_text",
    DetailType.AREA: "value_number",
    DetailType.DATE: "value_date",
}


def _value_matches_type() -> str:
    """Exactly the value column of the detail's type is filled."""
    cases = []
    for detail_type, column in _VALUE_COLUMNS.items():
        keys = ", ".join(f"'{k.value}'" for k, t in DETAIL_TYPES.items() if t is detail_type)
        filled = [f"{c} IS {'NOT ' if c == column else ''}NULL" for c in _VALUE_COLUMNS.values()]
        cases.append(f"(key IN ({keys}) AND {' AND '.join(filled)})")
    return " OR ".join(cases)


class ProjectDetail(IdMixin, TenantOwned, Base):
    """A built-in detail (A27) and its value, stored by the detail's type."""

    __tablename__ = "project_details"
    __table_args__ = (
        _project_fk("project_details"),
        UniqueConstraint("project_id", "key", name="uq_project_details_project_id_key"),
        UniqueConstraint(
            "project_id",
            "position",
            name="uq_project_details_project_id_position",
            deferrable=True,
            initially="DEFERRED",
        ),
        enum_check("key", DetailKey),
        CheckConstraint(_value_matches_type(), name="value_matches_type"),
        CheckConstraint(
            "value_text IS NULL OR length(btrim(value_text)) > 0", name="text_not_blank"
        ),
        CheckConstraint("value_number IS NULL OR value_number >= 0", name="number_not_negative"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(index=True)
    key: Mapped[DetailKey] = mapped_column(TextEnum(DetailKey))
    position: Mapped[int] = mapped_column()
    value_text: Mapped[str | None] = mapped_column(Text)
    value_number: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    value_date: Mapped[date | None] = mapped_column(Date)


class Meeting(IdMixin, TimestampsMixin, TenantOwned, Base):
    """A project's meetings. The client page shows the next one by date, so a past
    meeting simply stops being shown."""

    __tablename__ = "meetings"
    __table_args__ = (
        _project_fk("meetings"),
        CheckConstraint(
            f"length(btrim(title)) BETWEEN 1 AND {MEETING_TITLE_MAX}", name="title_length"
        ),
        CheckConstraint(
            f"location IS NULL OR length(location) <= {MEETING_LOCATION_MAX}",
            name="location_length",
        ),
        CheckConstraint("ends_at > starts_at", name="ends_after_start"),
        # Only web links: a `javascript:` link could run in a client's browser.
        CheckConstraint(r"link IS NULL OR link ~ '^https?://\S+$'", name="link_is_web"),
        Index("ix_meetings_project_id_starts_at", "project_id", "starts_at"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column()
    title: Mapped[str] = mapped_column(Text)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    location: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(Text)
