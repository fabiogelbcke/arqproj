"""Project settings in the painel: a cover per project; the app may change a
project's name, client, status and cover.

Revision: 0012
Previous: 0011
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = (
    "name, client_name, status, archived_from, "
    "cover_file_id, cover_type, cover_folder_id, row_version"
)


def upgrade() -> None:
    # The status before archiving: undoing an archive may only return to it.
    op.add_column("projects", sa.Column("archived_from", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_projects_archived_from_known"),
        "projects",
        "archived_from IN ('draft', 'active', 'completed')",
    )
    op.create_check_constraint(
        op.f("ck_projects_archived_from_set"),
        "projects",
        "(status = 'archived') = (archived_from IS NOT NULL)",
    )
    op.add_column("projects", sa.Column("cover_file_id", sa.Text(), nullable=True))
    op.add_column("projects", sa.Column("cover_type", sa.Text(), nullable=True))
    op.add_column("projects", sa.Column("cover_folder_id", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_projects_cover_type_known"),
        "projects",
        "cover_type IN ('image/png', 'image/jpeg', 'image/webp')",
    )
    op.create_check_constraint(
        op.f("ck_projects_cover_complete"),
        "projects",
        "(cover_file_id IS NULL) = (cover_type IS NULL)",
    )
    # Only these columns: the rest of a project changes in later steps.
    op.execute(
        f"""
        DO $$
        BEGIN
            EXECUTE format(
                'GRANT UPDATE ({_COLUMNS}) ON projects TO %I',
                current_database() || '_app'
            );
        END $$
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            EXECUTE format(
                'REVOKE UPDATE ({_COLUMNS}) ON projects FROM %I',
                current_database() || '_app'
            );
        END $$
        """
    )
    op.drop_constraint(op.f("ck_projects_cover_complete"), "projects", type_="check")
    op.drop_constraint(op.f("ck_projects_cover_type_known"), "projects", type_="check")
    op.drop_column("projects", "cover_folder_id")
    op.drop_column("projects", "cover_type")
    op.drop_column("projects", "cover_file_id")
    op.drop_constraint(op.f("ck_projects_archived_from_set"), "projects", type_="check")
    op.drop_constraint(op.f("ck_projects_archived_from_known"), "projects", type_="check")
    op.drop_column("projects", "archived_from")
