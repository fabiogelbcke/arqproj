"""Editing a project's content on its page (edit mode, part 1): description,
project type, details, the next meeting and stage notes.

Revision: 0015
Previous: 0014
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GRANTS = [
    "UPDATE (description, project_type, last_activity_at) ON projects",
    "INSERT, UPDATE, DELETE ON project_details",
    "INSERT, UPDATE, DELETE ON meetings",
    "UPDATE (notes, notes_updated_at) ON project_stages",
]


def _run(statement: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            EXECUTE format('{statement}', current_database() || '_app');
        END $$
        """
    )


def upgrade() -> None:
    for grant in GRANTS:
        _run(f"GRANT {grant} TO %I")


def downgrade() -> None:
    for grant in reversed(GRANTS):
        _run(f"REVOKE {grant} FROM %I")
