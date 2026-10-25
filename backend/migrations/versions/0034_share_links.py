"""Sharing files by link (A37, 25 Oct 2026).

`share_links` holds each link a client or staff member made from a project page,
as a hash of its token; `share_link_files` the exact versions it serves, by
storage identity. Both are isolated per office like every project table. The app
reads and adds links, turns them off, counts their downloads, and replaces a
link's files when it moves to newer versions.

Revision: 0034
Previous: 0033
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "share_links",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("files_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("downloads", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_download_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("day", sa.Date(), nullable=True),
        sa.Column("day_bytes", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id", sa.Uuid(), server_default=sa.text("current_tenant_id()"), nullable=False
        ),
        sa.CheckConstraint(
            "downloads >= 0 AND day_bytes >= 0", name=op.f("ck_share_links_counts_not_negative")
        ),
        sa.CheckConstraint(
            "label IS NULL OR (length(btrim(label)) > 0 AND length(label) <= 60)",
            name=op.f("ck_share_links_label_length"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "created_by"],
            ["users.tenant_id", "users.id"],
            name="fk_share_links_creator",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.id"],
            name="fk_share_links_project",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_share_links_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_share_links")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_share_links_tenant_id_id"),
        sa.UniqueConstraint("token_hash", name=op.f("uq_share_links_token_hash")),
    )
    op.create_index(op.f("ix_share_links_project_id"), "share_links", ["project_id"], unique=False)
    op.create_index(op.f("ix_share_links_tenant_id"), "share_links", ["tenant_id"], unique=False)
    op.create_table(
        "share_link_files",
        sa.Column("link_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "tenant_id", sa.Uuid(), server_default=sa.text("current_tenant_id()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "link_id"],
            ["share_links.tenant_id", "share_links.id"],
            name="fk_share_link_files_link",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_share_link_files_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_share_link_files")),
        sa.UniqueConstraint("link_id", "item_id", name="uq_share_link_files_link_id_item_id"),
    )
    op.create_index(
        op.f("ix_share_link_files_link_id"), "share_link_files", ["link_id"], unique=False
    )
    op.create_index(
        op.f("ix_share_link_files_tenant_id"), "share_link_files", ["tenant_id"], unique=False
    )

    for table in ("share_links", "share_link_files"):
        # Tenant isolation (from backend/migrations/snippets.py, pasted as it was).
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            "USING (tenant_id = current_tenant_id()) "
            "WITH CHECK (tenant_id = current_tenant_id())"
        )
    op.execute(
        "CREATE TRIGGER share_links_set_updated_at BEFORE UPDATE ON share_links "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.execute(
        """
        DO $$
        DECLARE app_role text := current_database() || '_app';
        BEGIN
            EXECUTE format('GRANT SELECT, INSERT, UPDATE (disabled_at, files_updated_at, '
                           'downloads, last_download_at, day, day_bytes) ON share_links TO %I',
                           app_role);
            EXECUTE format('GRANT SELECT, INSERT, DELETE ON share_link_files TO %I', app_role);
        END $$
        """
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_share_link_files_tenant_id"), table_name="share_link_files")
    op.drop_index(op.f("ix_share_link_files_link_id"), table_name="share_link_files")
    op.drop_table("share_link_files")
    op.drop_index(op.f("ix_share_links_tenant_id"), table_name="share_links")
    op.drop_index(op.f("ix_share_links_project_id"), table_name="share_links")
    op.drop_table("share_links")
