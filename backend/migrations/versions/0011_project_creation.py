"""Project creation: a one-time key per creation; the app may create projects.

Revision: 0011
Previous: 0010
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("creation_key", sa.Text(), nullable=True))
    op.create_unique_constraint(
        op.f("uq_projects_tenant_id_creation_key"), "projects", ["tenant_id", "creation_key"]
    )

    # Staff create projects from the painel: a project, its address and stages.
    op.execute(
        """
        DO $$
        BEGIN
            EXECUTE format(
                'GRANT INSERT ON projects, project_slugs, project_stages TO %I',
                current_database() || '_app'
            );
        END $$
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            EXECUTE format(
                'REVOKE INSERT ON projects, project_slugs, project_stages FROM %I',
                current_database() || '_app'
            );
        END $$
        """
    )
    op.drop_constraint(op.f("uq_projects_tenant_id_creation_key"), "projects", type_="unique")
    op.drop_column("projects", "creation_key")
