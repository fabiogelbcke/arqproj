"""One-time links for choosing a password (invites and resets), tenant-isolated.

Revision: 0005
Previous: 0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "password_links",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "tenant_id", sa.Uuid(), server_default=sa.text("current_tenant_id()"), nullable=False
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "kind IN ('invite', 'reset')", name=op.f("ck_password_links_kind_known")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_password_links_tenant_id_tenants")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            name=op.f("fk_password_links_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_password_links")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_password_links_token_hash")),
    )
    op.create_index("ix_password_links_tenant_id", "password_links", ["tenant_id"])
    op.create_index("ix_password_links_user_id", "password_links", ["user_id"])

    # Tenant isolation (from backend/migrations/snippets.py, pasted as it was).
    op.execute("ALTER TABLE password_links ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE password_links FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON password_links "
        "USING (tenant_id = current_tenant_id()) "
        "WITH CHECK (tenant_id = current_tenant_id())"
    )

    # The app reads links and marks them used, and may change an account's password
    # and nothing else about it. Links are created by owner-run commands for now.
    op.execute(
        """
        DO $$
        DECLARE app_role text := current_database() || '_app';
        BEGIN
            EXECUTE format('GRANT SELECT, UPDATE (used_at) ON password_links TO %I', app_role);
            EXECUTE format('GRANT UPDATE (password_hash) ON users TO %I', app_role);
        END $$
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            EXECUTE format('REVOKE UPDATE (password_hash) ON users FROM %I',
                           current_database() || '_app');
        END $$
        """
    )
    op.drop_table("password_links")
