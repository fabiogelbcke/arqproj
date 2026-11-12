"""Sign-ups confirmed by Google keep nothing their maker chose (audit #210,
10 Nov 2026).

`users.unconfirmed_signup`: made through a signup link (the shared member link
or an owner link, A36) and its address not confirmed since. Whoever signed up
typed the address, which may be a colleague's; when Google confirms such an
account, its sessions end and its password stops working. An account whose
email was changed in "Minha conta" is unconfirmed too, but was confirmed
before, so it is not marked and Google only confirms it.

Backfill: every account still unconfirmed is marked. That also marks an
account in the middle of an email change, which nothing stored tells apart;
all data is test data so far (Fabio), so the simple rule is enough. Isolation
is lifted for the update, as the migration login is bound by it.

The app may change the flag (confirming clears it).

Revision: 0054
Previous: 0053
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0054"
down_revision: str | None = "0053"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "unconfirmed_signup", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )
    op.execute("ALTER TABLE users NO FORCE ROW LEVEL SECURITY")  # every office's
    op.execute("UPDATE users SET unconfirmed_signup = true WHERE email_confirmed_at IS NULL")
    op.execute("ALTER TABLE users FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        DO $$
        BEGIN
            EXECUTE format('GRANT UPDATE (unconfirmed_signup) ON users TO %I',
                           current_database() || '_app');
        END $$
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            EXECUTE format('REVOKE UPDATE (unconfirmed_signup) ON users FROM %I',
                           current_database() || '_app');
        END $$
        """
    )
    op.drop_column("users", "unconfirmed_signup")
