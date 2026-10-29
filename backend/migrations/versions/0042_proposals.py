"""Proposals (A42, 28 Oct 2026).

- `projects.status` gains `proposal`: the client page shows only the proposal
  until staff mark it accepted.
- `office_profiles` gains the details a proposal prints (address, city, phone, WhatsApp,
  the signing architect) and the office's own opening and observations.
- `proposal_service_presets`: the services the office offers, as new proposals
  list them. `proposals`: each saved version of a project's proposal, as its
  content; the app only adds versions, never changes one.

Both new tables are isolated per office like every project table, and the
operator role may delete them with the office (A38).

Revision: 0042
Previous: 0041
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0042"
down_revision: str | None = "0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUSES_BEFORE = "'draft', 'active', 'completed', 'archived'"
# In the enum's order (ProjectStatus), as the models write the check.
STATUSES_AFTER = "'draft', 'proposal', 'active', 'completed', 'archived'"
ARCHIVED_FROM_BEFORE = "'draft', 'active', 'completed'"
ARCHIVED_FROM_AFTER = "'draft', 'proposal', 'active', 'completed'"
OFFICE_COLUMNS = (
    "address",
    "city",
    "phone",
    "whatsapp",
    "signatory",
    "proposal_intro",
    "proposal_notes",
)


def _statuses(statuses: str, archived_from: str) -> None:
    op.drop_constraint(op.f("ck_projects_status_known"), "projects")
    op.create_check_constraint(
        op.f("ck_projects_status_known"), "projects", f"status IN ({statuses})"
    )
    op.drop_constraint(op.f("ck_projects_archived_from_known"), "projects")
    op.create_check_constraint(
        op.f("ck_projects_archived_from_known"), "projects", f"archived_from IN ({archived_from})"
    )


def upgrade() -> None:
    _statuses(STATUSES_AFTER, ARCHIVED_FROM_AFTER)
    for column in OFFICE_COLUMNS:
        op.add_column("office_profiles", sa.Column(column, sa.Text(), nullable=True))

    op.create_table(
        "proposal_service_presets",
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
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
            "length(description) <= 1000",
            name=op.f("ck_proposal_service_presets_description_length"),
        ),
        sa.CheckConstraint(
            "position >= 1", name=op.f("ck_proposal_service_presets_position_positive")
        ),
        sa.CheckConstraint(
            "length(btrim(title)) BETWEEN 1 AND 80",
            name=op.f("ck_proposal_service_presets_title_length"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_proposal_service_presets_tenant_id_tenants"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_proposal_service_presets")),
    )
    op.create_index(
        op.f("ix_proposal_service_presets_tenant_id"),
        "proposal_service_presets",
        ["tenant_id"],
        unique=False,
    )
    op.create_table(
        "proposals",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
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
        sa.CheckConstraint(
            "jsonb_typeof(content) = 'object'", name=op.f("ck_proposals_content_is_object")
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_proposals_version_positive")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "created_by"],
            ["users.tenant_id", "users.id"],
            name="fk_proposals_creator",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.id"],
            name="fk_proposals_project",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_proposals_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_proposals")),
        sa.UniqueConstraint("project_id", "version", name="uq_proposals_project_id_version"),
    )
    op.create_index(op.f("ix_proposals_project_id"), "proposals", ["project_id"], unique=False)
    op.create_index(op.f("ix_proposals_tenant_id"), "proposals", ["tenant_id"], unique=False)

    for table in ("proposal_service_presets", "proposals"):
        # Tenant isolation (from backend/migrations/snippets.py, pasted as it was).
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            "USING (tenant_id = current_tenant_id()) "
            "WITH CHECK (tenant_id = current_tenant_id())"
        )
    op.execute(
        "CREATE TRIGGER proposal_service_presets_set_updated_at "
        "BEFORE UPDATE ON proposal_service_presets "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.execute(
        """
        DO $$
        DECLARE app_role text := current_database() || '_app';
                operator_role text := current_database() || '_operator';
        BEGIN
            EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON proposal_service_presets '
                           'TO %I', app_role);
            EXECUTE format('GRANT SELECT, INSERT ON proposals TO %I', app_role);
            EXECUTE format('GRANT SELECT, DELETE ON proposals, proposal_service_presets TO %I',
                           operator_role);
        END $$
        """
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_proposals_tenant_id"), table_name="proposals")
    op.drop_index(op.f("ix_proposals_project_id"), table_name="proposals")
    op.drop_table("proposals")
    op.drop_index(
        op.f("ix_proposal_service_presets_tenant_id"), table_name="proposal_service_presets"
    )
    op.drop_table("proposal_service_presets")
    for column in reversed(OFFICE_COLUMNS):
        op.drop_column("office_profiles", column)
    # A proposal goes back to being an ordinary active project, in every office.
    op.execute("ALTER TABLE projects NO FORCE ROW LEVEL SECURITY")
    op.execute("UPDATE projects SET status = 'active' WHERE status = 'proposal'")
    op.execute("UPDATE projects SET archived_from = 'active' WHERE archived_from = 'proposal'")
    op.execute("ALTER TABLE projects FORCE ROW LEVEL SECURITY")
    _statuses(STATUSES_BEFORE, ARCHIVED_FROM_BEFORE)
