"""Proposals (A42): the office's service presets, and each saved proposal.

A proposal is kept as its content (what staff filled in), one row per version;
its PDF is drawn from it whenever asked for, with the office's current logo.
Versions are only added: an earlier one stays as it was, for staff.
"""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base, CreatedAtMixin, IdMixin, TimestampsMixin
from backend.db.isolation import TenantOwned
from backend.projects.models import _project_fk

SERVICE_TITLE_MAX = 80
SERVICE_DESCRIPTION_MAX = 1000


class ProposalServicePreset(IdMixin, TimestampsMixin, TenantOwned, Base):
    """A service the office offers, as new proposals list it. An office without
    any starts from the built-in list (backend/i18n, `proposal.services`)."""

    __tablename__ = "proposal_service_presets"
    __table_args__ = (
        CheckConstraint("position >= 1", name="position_positive"),
        CheckConstraint(
            f"length(btrim(title)) BETWEEN 1 AND {SERVICE_TITLE_MAX}", name="title_length"
        ),
        CheckConstraint(
            f"length(description) <= {SERVICE_DESCRIPTION_MAX}", name="description_length"
        ),
    )

    position: Mapped[int] = mapped_column()
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)


class Proposal(IdMixin, CreatedAtMixin, TenantOwned, Base):
    """One saved version of a project's proposal. The client sees the latest."""

    __tablename__ = "proposals"
    __table_args__ = (
        _project_fk("proposals"),
        UniqueConstraint("project_id", "version", name="uq_proposals_project_id_version"),
        ForeignKeyConstraint(
            ["tenant_id", "created_by"],
            ["users.tenant_id", "users.id"],
            name="fk_proposals_creator",
        ),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint("jsonb_typeof(content) = 'object'", name="content_is_object"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(index=True)
    version: Mapped[int] = mapped_column()
    # backend.proposals.content.ProposalContent, as JSON: checked when saved.
    content: Mapped[dict] = mapped_column(JSONB)
    created_by: Mapped[uuid.UUID | None] = mapped_column()
