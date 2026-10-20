"""Staff accounts and their login sessions.

Each account belongs to one tenant (decision 15 Oct 2026, see the changelog): the
email is unique within the tenant, and the role is on the account. Both tables
are tenant tables under `tenant_isolation`, so another tenant's staff and
sessions simply do not exist for the app.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base, CreatedAtMixin, IdMixin, TimestampsMixin
from backend.db.isolation import TenantOwned
from backend.db.types import TextEnum, enum_check


class Role(StrEnum):
    OWNER = "owner"
    MEMBER = "member"


class User(IdMixin, TimestampsMixin, TenantOwned, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_users_tenant_id_email"),
        # Lets sessions reference (tenant_id, id), so a session's user is always
        # in the session's own tenant.
        UniqueConstraint("tenant_id", "id", name="uq_users_tenant_id_id"),
        CheckConstraint("email = lower(email) AND email LIKE '%_@_%'", name="email_format"),
        CheckConstraint("length(btrim(name)) > 0", name="name_not_blank"),
        enum_check("role", Role),
    )

    email: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    role: Mapped[Role] = mapped_column(TextEnum(Role), server_default=text("'member'"))
    # None until the person chooses one through an invite link, and for accounts
    # that will sign in only with Google (step 6).
    password_hash: Mapped[str | None] = mapped_column(Text)
    # When they finished or closed the project page's guided tour; None: not yet,
    # so it starts on their first project page (Fabio, 18 Oct 2026: per account).
    tour_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LoginSession(IdMixin, CreatedAtMixin, TenantOwned, Base):
    """A signed-in browser. The cookie holds a random token; only its hash is here."""

    __tablename__ = "sessions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            ondelete="CASCADE",
            name="fk_sessions_user",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    csrf_token: Mapped[str] = mapped_column(Text)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LinkKind(StrEnum):
    INVITE = "invite"  # a new account chooses its first password
    RESET = "reset"  # an existing account chooses a new one


class PasswordLink(IdMixin, CreatedAtMixin, TenantOwned, Base):
    """A one-time link for choosing a password. Only a hash of its token is here."""

    __tablename__ = "password_links"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            ondelete="CASCADE",
            name="fk_password_links_user",
        ),
        enum_check("kind", LinkKind),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    kind: Mapped[LinkKind] = mapped_column(TextEnum(LinkKind))
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class JoinLink(IdMixin, CreatedAtMixin, TenantOwned, Base):
    """An office's shared link for joining its staff (A36). Whoever opens it gives
    a name and an email and is emailed an invite link, so the email is proven
    theirs; they join as members. Only a hash of its token is here. At most one
    is on at a time: turning it off, or making a new one, sets `revoked_at`."""

    __tablename__ = "join_links"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "created_by"],
            ["users.tenant_id", "users.id"],
            ondelete="CASCADE",
            name="fk_join_links_creator",
        ),
        Index(
            "uq_join_links_one_on",
            "tenant_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )

    created_by: Mapped[uuid.UUID]
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
