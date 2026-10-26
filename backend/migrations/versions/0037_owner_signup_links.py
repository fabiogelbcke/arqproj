"""Command-created, one-time owner signup links (A36, approved 25 Oct 2026).

Existing shared links keep the member role, reusable 24-hour lifetime and one-on
index. Owner links have their own expiry and may exist before any user, so their
creator is NULL. Claiming one sets used_at atomically with account creation.
Column defaults fill existing rows without lifting tenant isolation.

Revision: 0037
Previous: 0036
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "join_links",
        sa.Column("role", sa.Text(), server_default=sa.text("'member'"), nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_join_links_role_known"), "join_links", "role IN ('owner', 'member')"
    )
    op.add_column(
        "join_links",
        sa.Column("single_use", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column("join_links", sa.Column("used_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("join_links", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.alter_column("join_links", "created_by", nullable=True)
    op.drop_index("uq_join_links_one_on", table_name="join_links")
    op.create_index(
        "uq_join_links_one_on",
        "join_links",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL AND role = 'member'"),
    )
    op.execute(
        """
        DO $$
        DECLARE app_role text := current_database() || '_app';
        BEGIN
            EXECUTE format('GRANT UPDATE (used_at) ON join_links TO %I', app_role);
        END $$
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE app_role text := current_database() || '_app';
        BEGIN
            EXECUTE format('REVOKE UPDATE (used_at) ON join_links FROM %I', app_role);
        END $$
        """
    )
    # Owner links cannot become reusable member links on downgrade. Remove them
    # for every tenant before restoring the unique index and required creator.
    op.execute("ALTER TABLE join_links NO FORCE ROW LEVEL SECURITY")
    op.execute("DELETE FROM join_links WHERE role = 'owner'")
    op.execute("ALTER TABLE join_links FORCE ROW LEVEL SECURITY")
    op.drop_index("uq_join_links_one_on", table_name="join_links")
    op.create_index(
        "uq_join_links_one_on",
        "join_links",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.alter_column("join_links", "created_by", nullable=False)
    op.drop_column("join_links", "expires_at")
    op.drop_column("join_links", "used_at")
    op.drop_column("join_links", "single_use")
    op.drop_constraint(op.f("ck_join_links_role_known"), "join_links", type_="check")
    op.drop_column("join_links", "role")
