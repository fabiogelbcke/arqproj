"""Built-in types and stages edited from the operator dashboard (A44, Fabio,
3 Nov 2026; schema change approved the same day).

- `project_type_stages` holds every stage a type lists, no longer only the ones it
  ticks: `usual` says which come ticked, and `about` (the type's own words) is
  optional, a stage without it using its general description. The stages each
  type listed without ticking were a table in the code until now; they are
  written here as they were. "Outro" keeps only its ticked one: it lists every
  stage.
- `hidden` on `project_types` and `stage_definitions`: not offered for new
  projects, kept by the projects that use them.
- The operator login may read, add and change these three tables (and remove a
  type's listed stages), and its audit events may name no office: a change to the
  whole site's lists has none.

Downgrade drops the stages listed without ticking (the code listed them before),
the hidden flags and the operator's rights; an audit event without an office, or a
ticked stage without its own words, stops it.

Revision: 0048
Previous: 0047
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0048"
down_revision: str | None = "0047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The 11 building stages, as the code listed them for the building types.
BUILDING = [
    "briefing",
    "survey",
    "feasibility_study",
    "preliminary_study",
    "schematic_design",
    "permit_documents",
    "construction_documents",
    "detailing",
    "coordination",
    "complementary_projects",
    "specifications",
]
LISTED = {
    "architecture": BUILDING,
    "interiors": [s for s in BUILDING if s not in ("feasibility_study", "permit_documents")],
    "renovation": BUILDING,
    "landscaping": BUILDING,
}
TABLES = "project_types, stage_definitions, project_type_stages"


def upgrade() -> None:
    op.add_column(
        "project_type_stages",
        sa.Column("usual", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.alter_column("project_type_stages", "about", nullable=True)
    for kind, stages in LISTED.items():
        keys = ", ".join(f"'{key}'" for key in stages)
        op.execute(
            f"""
            INSERT INTO project_type_stages (project_type, stage_key, about, usual)
            SELECT '{kind}', key, NULL, false FROM stage_definitions WHERE key IN ({keys})
            ON CONFLICT (project_type, stage_key) DO NOTHING
            """
        )
    for table in ("project_types", "stage_definitions"):
        op.add_column(
            table,
            sa.Column("hidden", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        )
    op.alter_column("operator_audit_events", "target_tenant_id", nullable=True)
    op.alter_column("operator_audit_events", "target_slug", nullable=True)
    op.execute(f"""
        DO $$
        DECLARE operator_role text := current_database() || '_operator';
        BEGIN
            EXECUTE format('GRANT SELECT, INSERT, UPDATE ON {TABLES} TO %I', operator_role);
            EXECUTE format('GRANT DELETE ON project_type_stages TO %I', operator_role);
        END $$
    """)


def downgrade() -> None:
    op.execute(f"""
        DO $$
        DECLARE operator_role text := current_database() || '_operator';
        BEGIN
            EXECUTE format('REVOKE SELECT, INSERT, UPDATE, DELETE ON {TABLES} FROM %I',
                           operator_role);
        END $$
    """)
    op.alter_column("operator_audit_events", "target_slug", nullable=False)
    op.alter_column("operator_audit_events", "target_tenant_id", nullable=False)
    for table in ("stage_definitions", "project_types"):
        op.drop_column(table, "hidden")
    op.execute("DELETE FROM project_type_stages WHERE NOT usual")
    op.alter_column("project_type_stages", "about", nullable=False)
    op.drop_column("project_type_stages", "usual")
