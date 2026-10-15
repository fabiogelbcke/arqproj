"""Staff accounts and their login sessions.

Each account belongs to one tenant (decision 15 Oct 2026, see the changelog): the
email is unique within the tenant, and the role is on the account. Both tables
are tenant tables under `tenant_isolation`, so another tenant's staff and
sessions simply do not exist for the app.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base, CreatedAtMixin, IdMixin, TimestampsMixin
from backend.db.isolation import TenantOwned

ROLES = ("owner", "member")


class User(IdMixin, TimestampsMixin, TenantOwned, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_users_tenant_id_email"),
        # Lets sessions reference (tenant_id, id), so a session's user is always
        # in the session's own tenant.
        UniqueConstraint("tenant_id", "id", name="uq_users_tenant_id_id"),
        CheckConstraint("email = lower(email) AND email LIKE '%_@_%'", name="email_format"),
        CheckConstraint("length(btrim(name)) > 0", name="name_not_blank"),
        CheckConstraint(f"role IN {ROLES}", name="role_known"),
    )

    email: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text, server_default=text("'member'"))
    # None for accounts that will sign in only with Google (step 6).
    password_hash: Mapped[str | None] = mapped_column(Text)


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
