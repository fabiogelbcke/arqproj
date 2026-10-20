"""Owners invite staff from the painel (A36, 20 Oct 2026).

The app may now create staff accounts (an invite makes one without a password)
and delete one whose invite is cancelled; until now only owner-run commands did.
`join_links` holds each office's shared link for joining, as a hash, at most one
on at a time.

Revision: 0030
Previous: 0029
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "join_links",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "tenant_id", sa.Uuid(), server_default=sa.text("current_tenant_id()"), nullable=False
        ),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_join_links_tenant_id_tenants")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "created_by"],
            ["users.tenant_id", "users.id"],
            name=op.f("fk_join_links_creator"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_join_links")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_join_links_token_hash")),
    )
    op.create_index("ix_join_links_tenant_id", "join_links", ["tenant_id"])
    op.create_index(
        "uq_join_links_one_on",
        "join_links",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )

    # Tenant isolation (from backend/migrations/snippets.py, pasted as it was).
    op.execute("ALTER TABLE join_links ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE join_links FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON join_links "
        "USING (tenant_id = current_tenant_id()) "
        "WITH CHECK (tenant_id = current_tenant_id())"
    )

    op.execute(
        """
        DO $$
        DECLARE app_role text := current_database() || '_app';
        BEGIN
            EXECUTE format('GRANT SELECT, INSERT, UPDATE (revoked_at) ON join_links TO %I',
                           app_role);
            EXECUTE format('GRANT INSERT, DELETE ON users TO %I', app_role);
        END $$
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            EXECUTE format('REVOKE INSERT, DELETE ON users FROM %I',
                           current_database() || '_app');
        END $$
        """
    )
    op.drop_table("join_links")
