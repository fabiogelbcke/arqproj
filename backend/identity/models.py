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
    Integer,
    Text,
    UniqueConstraint,
    func,
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
    # None while someone who joined through an office signup link hasn't shown
    # the address is theirs (a code or link emailed to it); until then they can
    # sign in only to confirm it (A36). Every other account starts confirmed: an
    # invite or reset link proves the address when it's used.
    email_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


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
    CONFIRM = "confirm"  # someone who joined through a signup link confirms their email


class PasswordLink(IdMixin, CreatedAtMixin, TenantOwned, Base):
    """A one-time link for choosing a password, or for confirming an email. Only a
    hash of its token is here; a confirmation also has a short code to type."""

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
    # A confirmation's 6-digit code, hashed with the link's token hash; wrong
    # codes typed count in `tries`, and enough of them use the link up.
    code_hash: Mapped[str | None] = mapped_column(Text)
    tries: Mapped[int] = mapped_column(Integer, server_default=text("0"))


class JoinLink(IdMixin, CreatedAtMixin, TenantOwned, Base):
    """Signup links (A36): the painel's shared member link, or a command's
    one-time owner link. Both require email confirmation before the account
    works. Only a hash of the token is stored. At most one member link is on;
    turning it off or making another sets `revoked_at`, without touching owners."""

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
            postgresql_where=text("revoked_at IS NULL AND role = 'member'"),
        ),
        enum_check("role", Role),
    )

    # A command can create the first owner's link before the tenant has users.
    created_by: Mapped[uuid.UUID | None]
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    role: Mapped[Role] = mapped_column(TextEnum(Role), server_default=text("'member'"))
    single_use: Mapped[bool] = mapped_column(server_default=text("false"))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # None keeps the shared member link's 24-hour lifetime.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
