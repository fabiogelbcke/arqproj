"""Project access and address from the painel (step 2.4): the app may change a
project's access mode, password and access version, and which of its addresses
is current.

Revision: 0014
Previous: 0013
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _grant(statement: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            EXECUTE format('{statement}', current_database() || '_app');
        END $$
        """
    )


def upgrade() -> None:
    _grant("GRANT UPDATE (access_mode, password_hash, access_version) ON projects TO %I")
    _grant("GRANT UPDATE (is_current) ON project_slugs TO %I")


def downgrade() -> None:
    _grant("REVOKE UPDATE (is_current) ON project_slugs FROM %I")
    _grant("REVOKE UPDATE (access_mode, password_hash, access_version) ON projects FROM %I")
