"""Staff accounts (one tenant each) and login sessions, both tenant-isolated.

Revision: 0003
Previous: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "tenant_id", sa.Uuid(), server_default=sa.text("current_tenant_id()"), nullable=False
        ),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), server_default=sa.text("'member'"), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "email = lower(email) AND email LIKE '%_@_%'", name=op.f("ck_users_email_format")
        ),
        sa.CheckConstraint("length(btrim(name)) > 0", name=op.f("ck_users_name_not_blank")),
        sa.CheckConstraint("role IN ('owner', 'member')", name=op.f("ck_users_role_known")),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_users_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("tenant_id", "email", name=op.f("uq_users_tenant_id_email")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_users_tenant_id_id")),
    )
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])
    op.execute(
        "CREATE TRIGGER users_set_updated_at BEFORE UPDATE ON users "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )

    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "tenant_id", sa.Uuid(), server_default=sa.text("current_tenant_id()"), nullable=False
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("csrf_token", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_sessions_tenant_id_tenants")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            name=op.f("fk_sessions_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_sessions_token_hash")),
    )
    op.create_index("ix_sessions_tenant_id", "sessions", ["tenant_id"])
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])

    # Tenant isolation (from backend/migrations/snippets.py, pasted as it was).
    for table in ("users", "sessions"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            "USING (tenant_id = current_tenant_id()) "
            "WITH CHECK (tenant_id = current_tenant_id())"
        )

    # The app reads accounts (to sign people in) and manages sessions; accounts are
    # created and changed only by owner-run commands for now.
    op.execute(
        """
        DO $$
        DECLARE app_role text := current_database() || '_app';
        BEGIN
            EXECUTE format('GRANT SELECT ON users TO %I', app_role);
            EXECUTE format('GRANT SELECT, INSERT, UPDATE ON sessions TO %I', app_role);
        END $$
        """
    )


def downgrade() -> None:
    op.drop_table("sessions")
    op.drop_table("users")
