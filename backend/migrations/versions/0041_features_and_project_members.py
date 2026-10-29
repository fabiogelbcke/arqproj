"""Features switched on per office (A40), and who works on each project (A41).

`tenants.features` lists the features the operator switched on for an office;
only the operator role may change it. `project_members` holds the staff working
on each project, isolated per office like every project table; the app reads,
adds and removes them, and the operator role deletes them with the office.

Revision: 0041
Previous: 0040
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0041"
down_revision: str | None = "0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column(
            "features",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )
    op.create_table(
        "project_members",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id", sa.Uuid(), server_default=sa.text("current_tenant_id()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.id"],
            name="fk_project_members_project",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_project_members_user",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_project_members_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_members")),
        sa.UniqueConstraint("project_id", "user_id", name="uq_project_members_project_id_user_id"),
    )
    op.create_index(op.f("ix_project_members_project_id"), "project_members", ["project_id"])
    op.create_index(op.f("ix_project_members_tenant_id"), "project_members", ["tenant_id"])
    op.create_index(op.f("ix_project_members_user_id"), "project_members", ["user_id"])
    # Tenant isolation (from backend/migrations/snippets.py, pasted as it was).
    op.execute("ALTER TABLE project_members ALTER COLUMN tenant_id SET DEFAULT current_tenant_id()")
    op.execute("ALTER TABLE project_members ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE project_members FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON project_members "
        "USING (tenant_id = current_tenant_id()) "
        "WITH CHECK (tenant_id = current_tenant_id())"
    )
    op.execute(
        "DO $$ BEGIN EXECUTE format("
        "'GRANT SELECT, INSERT, DELETE ON project_members TO %I', "
        "current_database() || '_app'"
        "); END $$"
    )
    op.execute("""
        DO $$
        DECLARE operator_role text := current_database() || '_operator';
        BEGIN
            EXECUTE format('GRANT UPDATE (features) ON tenants TO %I', operator_role);
            EXECUTE format('GRANT SELECT, DELETE ON project_members TO %I', operator_role);
        END $$
    """)


def downgrade() -> None:
    op.drop_index(op.f("ix_project_members_user_id"), table_name="project_members")
    op.drop_index(op.f("ix_project_members_tenant_id"), table_name="project_members")
    op.drop_index(op.f("ix_project_members_project_id"), table_name="project_members")
    op.drop_table("project_members")
    op.drop_column("tenants", "features")
