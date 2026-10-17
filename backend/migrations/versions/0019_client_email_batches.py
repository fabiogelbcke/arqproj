"""Client email batches and deliveries (A12, A32, plan section 14).

`notification_batches` gathers a project's changes into one email: at most one
open per project, due 45 minutes after the last change or 2 hours after the
first. `notification_deliveries` is that email to each address, sent once
whatever the retries; kept by address, so editing the recipients can't resend
it. `project_events.batch_id` says which email a change went into. The app
reads, adds and updates these; it never deletes them. Changes recorded before
this migration are marked as already handled: never emailed.

Revision: 0019
Previous: 0018
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


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


def _timestamps() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "notification_batches",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.Text(), server_default=sa.text("'open'"), nullable=False),
        sa.Column("first_event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        *_timestamps(),
        sa.Column(
            "tenant_id", sa.Uuid(), server_default=sa.text("current_tenant_id()"), nullable=False
        ),
        sa.CheckConstraint(
            "state IN ('open', 'sending', 'sent', 'dropped')",
            name=op.f("ck_notification_batches_state_known"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.id"],
            name="fk_notification_batches_project",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_notification_batches_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_batches")),
    )
    op.create_index(
        op.f("ix_notification_batches_project_id"), "notification_batches", ["project_id"]
    )
    op.create_index(
        op.f("ix_notification_batches_tenant_id"), "notification_batches", ["tenant_id"]
    )
    op.create_index(
        "uq_notification_batches_open_per_project",
        "notification_batches",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("state = 'open'"),
    )
    op.execute(
        "CREATE TRIGGER notification_batches_set_updated_at BEFORE UPDATE ON "
        "notification_batches FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    _isolate_and_grant("notification_batches", "SELECT, INSERT, UPDATE")

    op.create_table(
        "notification_deliveries",
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("provider_id", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        *_timestamps(),
        sa.Column(
            "tenant_id", sa.Uuid(), server_default=sa.text("current_tenant_id()"), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('sent', 'failed')", name=op.f("ck_notification_deliveries_status_known")
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["notification_batches.id"],
            name=op.f("fk_notification_deliveries_batch_id_notification_batches"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_notification_deliveries_tenant_id_tenants"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_deliveries")),
        sa.UniqueConstraint(
            "batch_id",
            "email",
            name="uq_notification_deliveries_batch_id_email",
        ),
    )
    op.create_index(
        op.f("ix_notification_deliveries_batch_id"), "notification_deliveries", ["batch_id"]
    )
    op.create_index(
        op.f("ix_notification_deliveries_tenant_id"), "notification_deliveries", ["tenant_id"]
    )
    op.execute(
        "CREATE TRIGGER notification_deliveries_set_updated_at BEFORE UPDATE ON "
        "notification_deliveries FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    _isolate_and_grant("notification_deliveries", "SELECT, INSERT, UPDATE")

    op.add_column("project_events", sa.Column("batch_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_project_events_batch_id_notification_batches"),
        "project_events",
        "notification_batches",
        ["batch_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute(
        "DO $$ BEGIN EXECUTE format("
        "'GRANT UPDATE (batch_id) ON project_events TO %I', current_database() || '_app'"
        "); END $$"
    )

    # Changes recorded before emails existed (0018 onwards) are history, not news:
    # each project's go into one batch already closed, so the first pass emails
    # none of them. On Cloud SQL the migration login is no superuser, so the forced
    # tenant policy would hide every office's rows: lifted for these statements,
    # inside this transaction, then restored (as 0008).
    for table in ("project_events", "notification_batches"):
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
    op.execute(
        "INSERT INTO notification_batches "
        "(tenant_id, project_id, state, first_event_at, last_event_at, closed_at) "
        "SELECT tenant_id, project_id, 'dropped', min(occurred_at), max(occurred_at), now() "
        "FROM project_events GROUP BY tenant_id, project_id"
    )
    op.execute(
        "UPDATE project_events e SET batch_id = b.id "
        "FROM notification_batches b WHERE b.project_id = e.project_id"
    )
    for table in ("project_events", "notification_batches"):
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_project_events_batch_id_notification_batches"),
        "project_events",
        type_="foreignkey",
    )
    op.drop_column("project_events", "batch_id")
    op.drop_table("notification_deliveries")
    op.drop_table("notification_batches")
