"""Switching an office's Google Drive account (Fabio, 18 Oct 2026).

Another account can't reach the old folders, so each project gets a new, empty
folder in the new account: the app may now change `projects.folder_id` (it may
already change its stages' folders and its cover).

Revision: 0029
Previous: 0028
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            EXECUTE format('GRANT UPDATE (folder_id) ON projects TO %I',
                           current_database() || '_app');
        END $$
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            EXECUTE format('REVOKE UPDATE (folder_id) ON projects FROM %I',
                           current_database() || '_app');
        END $$
        """
    )
