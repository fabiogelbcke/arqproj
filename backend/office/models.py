"""An office's details, edited by its owners.

Kept apart from `tenants`, the address registry: that table is shared by every
office and only readable by the app, so letting the app change it would let one
office rename another. This one is isolated per office like any office data.
"""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import CheckConstraint, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base, IdMixin, TimestampsMixin
from backend.db.isolation import TenantOwned
from backend.db.types import TextEnum, enum_check

NAME_MAX = 80


class LogoType(StrEnum):
    PNG = "image/png"
    JPEG = "image/jpeg"
    WEBP = "image/webp"
    SVG = "image/svg+xml"


class OfficeProfile(IdMixin, TimestampsMixin, TenantOwned, Base):
    __tablename__ = "office_profiles"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_office_profiles_tenant_id"),
        CheckConstraint(
            f"length(btrim(display_name)) BETWEEN 1 AND {NAME_MAX}", name="display_name_length"
        ),
        CheckConstraint(
            "contact_email IS NULL OR (contact_email = lower(contact_email) "
            "AND contact_email LIKE '%_@_%.__%')",
            name="contact_email_format",
        ),
        enum_check("logo_type", LogoType),
        CheckConstraint("(logo_file_id IS NULL) = (logo_type IS NULL)", name="logo_complete"),
        enum_check("logo_dark_type", LogoType),
        CheckConstraint(
            "(logo_dark_file_id IS NULL) = (logo_dark_type IS NULL)", name="logo_dark_complete"
        ),
    )

    # Shown at the top of client pages and in the browser tab.
    display_name: Mapped[str] = mapped_column(Text)
    # Reply-to address of client emails (slice 5).
    contact_email: Mapped[str | None] = mapped_column(Text)
    # The logo, in the office's storage: a Drive file id, or a local path.
    logo_file_id: Mapped[str | None] = mapped_column(Text)
    logo_type: Mapped[LogoType | None] = mapped_column(TextEnum(LogoType))
    # For an SVG logo, a PNG of it drawn by the painel's browser: email programs
    # don't show SVG (A32). None for other logos, which email as they are.
    logo_png_file_id: Mapped[str | None] = mapped_column(Text)
    # The logo for dark mode; None: the logo above shows in dark mode too.
    logo_dark_file_id: Mapped[str | None] = mapped_column(Text)
    logo_dark_type: Mapped[LogoType | None] = mapped_column(TextEnum(LogoType))
    # The `_marca` folder holding them, inside the office's root folder.
    brand_folder_id: Mapped[str | None] = mapped_column(Text)
