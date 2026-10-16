"""Client email updates (A32): the addresses staff list for each project.

`project_recipients` holds each project's addresses, entered in the Projeto
dialog. An address the client unsubscribed stays, marked so, and is never written
to again (section 14). Isolated per office like every project table; the app
reads, adds, removes and marks them.

Revision: 0017
Previous: 0016
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_recipients",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'subscribed'"), nullable=False),
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
            "email = lower(email) AND email LIKE '%_@_%.__%' AND length(email) <= 254",
            name=op.f("ck_project_recipients_email_format"),
        ),
        sa.CheckConstraint(
            "status IN ('subscribed', 'unsubscribed')",
            name=op.f("ck_project_recipients_status_known"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.id"],
            name="fk_project_recipients_project",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_project_recipients_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_recipients")),
        sa.UniqueConstraint("project_id", "email", name="uq_project_recipients_project_id_email"),
    )
    op.create_index(op.f("ix_project_recipients_project_id"), "project_recipients", ["project_id"])
    op.create_index(op.f("ix_project_recipients_tenant_id"), "project_recipients", ["tenant_id"])
    op.execute(
        "CREATE TRIGGER project_recipients_set_updated_at BEFORE UPDATE ON project_recipients "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    # Tenant isolation (from backend/migrations/snippets.py, pasted as it was).
    op.execute(
        "ALTER TABLE project_recipients ALTER COLUMN tenant_id SET DEFAULT current_tenant_id()"
    )
    op.execute("ALTER TABLE project_recipients ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE project_recipients FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON project_recipients "
        "USING (tenant_id = current_tenant_id()) "
        "WITH CHECK (tenant_id = current_tenant_id())"
    )
    op.execute(
        "DO $$ BEGIN EXECUTE format("
        "'GRANT SELECT, INSERT, UPDATE, DELETE ON project_recipients TO %I', "
        "current_database() || '_app'"
        "); END $$"
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_project_recipients_tenant_id"), table_name="project_recipients")
    op.drop_index(op.f("ix_project_recipients_project_id"), table_name="project_recipients")
    op.drop_table("project_recipients")
