"""Storage connections (one per office, tenant-isolated); folders of projects and stages.

Revision: 0007
Previous: 0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "storage_connections",
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("root_id", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("reader_identity", sa.Text(), nullable=True),
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
            "kind <> 'google' OR reader_identity IS NOT NULL",
            name=op.f("ck_storage_connections_google_has_reader"),
        ),
        sa.CheckConstraint(
            "kind IN ('google', 'folder')", name=op.f("ck_storage_connections_kind_known")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_storage_connections_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_storage_connections")),
        sa.UniqueConstraint("tenant_id", name="uq_storage_connections_tenant_id"),
    )
    op.create_index(
        op.f("ix_storage_connections_tenant_id"), "storage_connections", ["tenant_id"], unique=False
    )
    op.add_column("project_stages", sa.Column("folder_id", sa.Text(), nullable=True))
    op.add_column("projects", sa.Column("folder_id", sa.Text(), nullable=True))

    op.execute(
        "CREATE TRIGGER storage_connections_set_updated_at BEFORE UPDATE ON storage_connections "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    # Tenant isolation (from backend/migrations/snippets.py, pasted as it was).
    op.execute("ALTER TABLE storage_connections ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE storage_connections FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON storage_connections "
        "USING (tenant_id = current_tenant_id()) "
        "WITH CHECK (tenant_id = current_tenant_id())"
    )
    # The app reads which store an office uses; offices set it up through
    # owner-run commands for now (slice 3 adds the painel's connection screen).
    op.execute(
        """
        DO $$
        BEGIN
            EXECUTE format(
                'GRANT SELECT ON storage_connections TO %I', current_database() || '_app'
            );
        END $$
        """
    )


def downgrade() -> None:
    op.drop_column("project_stages", "folder_id")
    op.drop_column("projects", "folder_id")
    op.drop_table("storage_connections")
