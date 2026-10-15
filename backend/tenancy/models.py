"""Offices (tenants) and the addresses they are reached on.

Each office has exactly one primary address: the one links and emails use. Other
addresses are aliases that redirect to it (an old domain after a rebrand, the
product subdomain next to a custom domain). `www.` is handled in code, not here.
"""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base, CreatedAtMixin, IdMixin, TimestampsMixin

TENANT_STATUSES = ("active", "suspended")


class Tenant(IdMixin, TimestampsMixin, Base):
    __tablename__ = "tenants"
    __table_args__ = (
        CheckConstraint(r"slug ~ '^[a-z0-9]([a-z0-9-]*[a-z0-9])?$'", name="slug_format"),
        CheckConstraint("length(btrim(name)) > 0", name="name_not_blank"),
        CheckConstraint(f"status IN {TENANT_STATUSES}", name="status_known"),
    )

    slug: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    locale: Mapped[str] = mapped_column(Text, server_default=text("'pt-BR'"))
    timezone: Mapped[str] = mapped_column(Text, server_default=text("'America/Sao_Paulo'"))
    status: Mapped[str] = mapped_column(Text, server_default=text("'active'"))

    domains: Mapped[list[TenantDomain]] = relationship(back_populates="tenant")


class TenantDomain(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "tenant_domains"
    __table_args__ = (
        # Stored normalised, so lookups are exact: lowercase letters, digits, dots and
        # hyphens only; no scheme, port or trailing dot.
        CheckConstraint(r"hostname ~ '^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$'", name="hostname_format"),
        Index("ix_tenant_domains_tenant_id", "tenant_id"),
        # At most one primary address per office.
        Index(
            "uq_tenant_domains_one_primary",
            "tenant_id",
            unique=True,
            postgresql_where=text("is_primary"),
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    # Unique across all offices: one address can never point at two offices.
    hostname: Mapped[str] = mapped_column(Text, unique=True)
    is_primary: Mapped[bool] = mapped_column(server_default=text("false"))

    tenant: Mapped[Tenant] = relationship(back_populates="domains")
