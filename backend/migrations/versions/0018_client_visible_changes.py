"""Client-visible changes (A28) and the files each project has shown (A10).

`project_events` records each change a client can notice: a file shown for the
first time (found by the maintenance scan), a stage advanced, the project
completed, a meeting scheduled, changed or removed, a stage's note. Emails,
"Atualizado" and the updates panel read it. `project_files_seen` lists the files a
project's page has shown, so the scan knows which are new. `projects` gains
`files_scanned_at`: a project's first scan only records what is there.

The app adds rows to both tables and never edits them; it may set a project's
`files_scanned_at` (and `last_activity_at`, granted in 0015).

Revision: 0018
Previous: 0017
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS = (
    "'file_published', 'stage_advanced', 'project_completed', 'meeting_scheduled', "
    "'meeting_changed', 'meeting_cleared', 'note_changed'"
)


def _isolate_and_grant(table: str, privileges: str) -> None:
    # Tenant isolation (from backend/migrations/snippets.py, pasted as it was).
    op.execute(f"ALTER TABLE {table} ALTER COLUMN tenant_id SET DEFAULT current_tenant_id()")
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON {table} "
        "USING (tenant_id = current_tenant_id()) "
        "WITH CHECK (tenant_id = current_tenant_id())"
    )
    op.execute(
        "DO $$ BEGIN EXECUTE format("
        f"'GRANT {privileges} ON {table} TO %I', current_database() || '_app'"
        "); END $$"
    )


def upgrade() -> None:
    op.create_table(
        "project_events",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("stage_position", sa.Integer(), nullable=True),
        sa.Column("item_id", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "tenant_id", sa.Uuid(), server_default=sa.text("current_tenant_id()"), nullable=False
        ),
        sa.CheckConstraint(f"kind IN ({KINDS})", name=op.f("ck_project_events_kind_known")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.id"],
            name="fk_project_events_project",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_project_events_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_events")),
    )
    op.create_index(
        "ix_project_events_project_id_occurred_at",
        "project_events",
        ["project_id", "occurred_at"],
    )
    op.create_index(op.f("ix_project_events_tenant_id"), "project_events", ["tenant_id"])
    _isolate_and_grant("project_events", "SELECT, INSERT")

    op.create_table(
        "project_files_seen",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Text(), nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "tenant_id", sa.Uuid(), server_default=sa.text("current_tenant_id()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.id"],
            name="fk_project_files_seen_project",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_project_files_seen_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_files_seen")),
        sa.UniqueConstraint(
            "project_id", "item_id", name="uq_project_files_seen_project_id_item_id"
        ),
    )
    op.create_index(op.f("ix_project_files_seen_tenant_id"), "project_files_seen", ["tenant_id"])
    _isolate_and_grant("project_files_seen", "SELECT, INSERT")

    op.add_column(
        "projects", sa.Column("files_scanned_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute(
        "DO $$ BEGIN EXECUTE format("
        "'GRANT UPDATE (files_scanned_at) ON projects TO %I', current_database() || '_app'"
        "); END $$"
    )


def downgrade() -> None:
    op.drop_column("projects", "files_scanned_at")
    op.drop_index(op.f("ix_project_files_seen_tenant_id"), table_name="project_files_seen")
    op.drop_table("project_files_seen")
    op.drop_index(op.f("ix_project_events_tenant_id"), table_name="project_events")
    op.drop_index("ix_project_events_project_id_occurred_at", table_name="project_events")
    op.drop_table("project_events")
