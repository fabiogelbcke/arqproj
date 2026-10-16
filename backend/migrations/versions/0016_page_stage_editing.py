"""Editing a project's stages and progress on its page (edit mode, part 2).

Revision: 0016
Previous: 0015
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GRANTS = [
    "UPDATE (position, builtin_key, title, about, folder_id) ON project_stages",
    "DELETE ON project_stages",
    "UPDATE (current_position) ON projects",
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
