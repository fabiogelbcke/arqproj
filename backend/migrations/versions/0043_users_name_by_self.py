"""A staff member changes their own name ("Minha conta", Fabio, 28 Oct 2026).

The app may now set `users.name`, as it may set `password_hash`, `tour_seen_at`,
`email` and `email_confirmed_at`; nothing else about users.

Revision: 0043
Previous: 0042
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0043"
down_revision: str | None = "0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            EXECUTE format('GRANT UPDATE (name) ON users TO %I', current_database() || '_app');
        END $$
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            EXECUTE format('REVOKE UPDATE (name) ON users FROM %I', current_database() || '_app');
        END $$
        """
    )
