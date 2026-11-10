"""Client updates by WhatsApp (A47).

`project_whatsapp_recipients` holds each project's client numbers and where each
stands (invited by staff, subscribed, declined, unreachable); `whatsapp_deliveries`
records each batch's message to each number, as `notification_deliveries` does
for emails. Both are isolated per office like every project table.

`whatsapp_opt_outs` belongs to no office: a number that replied SAIR gets no
WhatsApp updates from any project, since they all come from one Unio number. It
holds only a keyed hash of the number, dated by the latest SAIR: a project the
client chose again after it gets updates again. The app reads, adds and re-dates rows.
`whatsapp_messages_seen`, no office's either, holds the ids of messages Meta's
webhook brought that were handled, so one delivered again is handled once.

Revision: 0054
Previous: 0053
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0054"
down_revision: str | None = "0053"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _isolate(table: str, privileges: str) -> None:
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
        "whatsapp_opt_outs",
        sa.Column("phone_hash", sa.Text(), nullable=False),
        sa.Column(
            "stopped_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("phone_hash", name=op.f("pk_whatsapp_opt_outs")),
    )
    op.execute(
        "DO $$ BEGIN EXECUTE format("
        "'GRANT SELECT, INSERT, UPDATE ON whatsapp_opt_outs TO %I', "
        "current_database() || '_app'"
        "); END $$"
    )
    op.create_table(
        "whatsapp_messages_seen",
        sa.Column("message_id", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("message_id", name=op.f("pk_whatsapp_messages_seen")),
    )
    op.execute(
        "DO $$ BEGIN EXECUTE format("
        "'GRANT SELECT, INSERT ON whatsapp_messages_seen TO %I', current_database() || '_app'"
        "); END $$"
    )
    op.create_table(
        "project_whatsapp_recipients",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("greeted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reinvited_at", sa.DateTime(timezone=True), nullable=True),
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
            "phone ~ '^[1-9][0-9]{7,14}$'",
            name=op.f("ck_project_whatsapp_recipients_phone_format"),
        ),
        sa.CheckConstraint(
            "source IN ('client', 'staff')",
            name=op.f("ck_project_whatsapp_recipients_source_known"),
        ),
        sa.CheckConstraint(
            "status IN ('invited', 'subscribed', 'declined', 'unreachable')",
            name=op.f("ck_project_whatsapp_recipients_status_known"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.id"],
            name="fk_project_whatsapp_recipients_project",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_project_whatsapp_recipients_tenant_id_tenants"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_whatsapp_recipients")),
        sa.UniqueConstraint(
            "project_id", "phone", name="uq_project_whatsapp_recipients_project_id_phone"
        ),
    )
    op.create_index(
        op.f("ix_project_whatsapp_recipients_project_id"),
        "project_whatsapp_recipients",
        ["project_id"],
    )
    op.create_index(
        op.f("ix_project_whatsapp_recipients_tenant_id"),
        "project_whatsapp_recipients",
        ["tenant_id"],
    )
    _isolate("project_whatsapp_recipients", "SELECT, INSERT, UPDATE, DELETE")
    op.execute(
        "CREATE TRIGGER project_whatsapp_recipients_set_updated_at "
        "BEFORE UPDATE ON project_whatsapp_recipients "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_table(
        "whatsapp_deliveries",
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("provider_id", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
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
            "status IN ('pending', 'sent', 'failed')",
            name=op.f("ck_whatsapp_deliveries_status_known"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["notification_batches.tenant_id", "notification_batches.id"],
            name="fk_whatsapp_deliveries_batch",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_whatsapp_deliveries_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_whatsapp_deliveries")),
        sa.UniqueConstraint("batch_id", "phone", name="uq_whatsapp_deliveries_batch_id_phone"),
    )
    op.create_index(op.f("ix_whatsapp_deliveries_batch_id"), "whatsapp_deliveries", ["batch_id"])
    op.create_index(op.f("ix_whatsapp_deliveries_tenant_id"), "whatsapp_deliveries", ["tenant_id"])
    _isolate("whatsapp_deliveries", "SELECT, INSERT, UPDATE")
    op.execute(
        "CREATE TRIGGER whatsapp_deliveries_set_updated_at "
        "BEFORE UPDATE ON whatsapp_deliveries "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    # Deleting an office (A38) removes its rows too.
    op.execute("""
        DO $$
        DECLARE operator_role text := current_database() || '_operator';
        BEGIN
            EXECUTE format('GRANT SELECT, DELETE ON project_whatsapp_recipients TO %I',
                operator_role);
            EXECUTE format('GRANT SELECT, DELETE ON whatsapp_deliveries TO %I', operator_role);
        END $$
    """)


def downgrade() -> None:
    op.drop_index(op.f("ix_whatsapp_deliveries_tenant_id"), table_name="whatsapp_deliveries")
    op.drop_index(op.f("ix_whatsapp_deliveries_batch_id"), table_name="whatsapp_deliveries")
    op.drop_table("whatsapp_deliveries")
    op.drop_index(
        op.f("ix_project_whatsapp_recipients_tenant_id"), table_name="project_whatsapp_recipients"
    )
    op.drop_index(
        op.f("ix_project_whatsapp_recipients_project_id"), table_name="project_whatsapp_recipients"
    )
    op.drop_table("project_whatsapp_recipients")
    op.drop_table("whatsapp_messages_seen")
    op.drop_table("whatsapp_opt_outs")
