"""The project page's guided tour, remembered per account (Fabio, 18 Oct 2026).

`users.tour_seen_at`: when the person finished or closed it; None until then.
The app may set it (as it may set `password_hash`), and nothing else about users.

Revision: 0027
Previous: 0026
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("tour_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        """
        DO $$
        BEGIN
            EXECUTE format('GRANT UPDATE (tour_seen_at) ON users TO %I',
                           current_database() || '_app');
        END $$
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            EXECUTE format('REVOKE UPDATE (tour_seen_at) ON users FROM %I',
                           current_database() || '_app');
        END $$
        """
    )
    op.drop_column("users", "tour_seen_at")
