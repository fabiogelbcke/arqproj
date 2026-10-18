""" "Esqueceu a senha?": the app makes reset links itself (it emails them).

Until now only owner-run commands created links. The app may now insert one, for
its own office only (row-level security's WITH CHECK); it retires earlier links
by marking them used, which it already may, so it still may not delete any.

Revision: 0026
Previous: 0025
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            EXECUTE format('GRANT INSERT ON password_links TO %I', current_database() || '_app');
        END $$
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            EXECUTE format('REVOKE INSERT ON password_links FROM %I', current_database() || '_app');
        END $$
        """
    )
