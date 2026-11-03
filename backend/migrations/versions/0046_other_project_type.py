""" "Outro" (A27, Fabio, 2 Nov 2026): a sixth built-in type whose name the office
types per project, kept in `projects.custom_type`. A built-in type never has one;
"Outro" always does. Its usual stage is Briefing; it lists every stage.

The app may insert any column of `projects` already; it is given UPDATE on this
one, for renaming the type or switching to or from "Outro" on the project page.

Downgrade removes the column and the type; a project of this type stops it (it
references the type), as it should.

Revision: 0046
Previous: 0045
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0046"
down_revision: str | None = "0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    project_types = sa.table(
        "project_types",
        sa.column("key", sa.Text()),
        sa.column("position", sa.Integer()),
        sa.column("labels", JSONB()),
    )
    op.bulk_insert(
        project_types,
        [{"key": "other", "position": 6, "labels": {"pt-BR": "Outro", "en": "Other"}}],
    )
    type_stages = sa.table(
        "project_type_stages",
        sa.column("project_type", sa.Text()),
        sa.column("stage_key", sa.Text()),
        sa.column("about", JSONB()),
    )
    op.bulk_insert(
        type_stages,
        [
            {
                "project_type": "other",
                "stage_key": "briefing",
                "about": {
                    "pt-BR": "Levantamento das necessidades, expectativas e orçamento do cliente.",
                    "en": "The client's needs, expectations and budget.",
                },
            }
        ],
    )
    op.add_column("projects", sa.Column("custom_type", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_projects_custom_type_named"),
        "projects",
        "(project_type = 'other') = (custom_type IS NOT NULL)",
    )
    op.create_check_constraint(
        op.f("ck_projects_custom_type_length"),
        "projects",
        "custom_type IS NULL OR length(btrim(custom_type)) BETWEEN 1 AND 80",
    )
    op.execute(
        """
        DO $$
        BEGIN
            EXECUTE format('GRANT UPDATE (custom_type) ON projects TO %I',
                           current_database() || '_app');
        END $$
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            EXECUTE format('REVOKE UPDATE (custom_type) ON projects FROM %I',
                           current_database() || '_app');
        END $$
        """
    )
    op.drop_constraint(op.f("ck_projects_custom_type_length"), "projects", type_="check")
    op.drop_constraint(op.f("ck_projects_custom_type_named"), "projects", type_="check")
    op.drop_column("projects", "custom_type")
    op.execute("DELETE FROM project_types WHERE key = 'other'")  # its type stage goes too
