"""Joining through the office's shared link: a password at once, then the email
confirmed with a code (A36, revised 25 Oct 2026).

`users.email_confirmed_at`: None while someone who joined through the shared link
hasn't confirmed their address. Its default fills every existing account and every
new one (an invite or reset link proves the address); only the shared link sets
it to NULL. Adding the column with a default fills existing rows without reading
them, so the isolation policy needs no lifting.

`password_links` gets a third kind, `confirm`, with its code's hash and the wrong
codes typed. The app may set `email_confirmed_at`, correct an unconfirmed email
(`email`), and count `tries`.

Revision: 0035
Previous: 0034
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "email_confirmed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
    )
    op.add_column("password_links", sa.Column("code_hash", sa.Text(), nullable=True))
    op.add_column(
        "password_links",
        sa.Column("tries", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.drop_constraint(op.f("ck_password_links_kind_known"), "password_links", type_="check")
    op.create_check_constraint(
        op.f("ck_password_links_kind_known"),
        "password_links",
        "kind IN ('invite', 'reset', 'confirm')",
    )
    op.execute(
        """
        DO $$
        DECLARE app_role text := current_database() || '_app';
        BEGIN
            EXECUTE format('GRANT UPDATE (email_confirmed_at, email) ON users TO %I', app_role);
            EXECUTE format('GRANT UPDATE (tries) ON password_links TO %I', app_role);
        END $$
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE app_role text := current_database() || '_app';
        BEGIN
            EXECUTE format('REVOKE UPDATE (tries) ON password_links FROM %I', app_role);
            EXECUTE format('REVOKE UPDATE (email_confirmed_at, email) ON users FROM %I',
                           app_role);
        END $$
        """
    )
    op.execute("ALTER TABLE password_links NO FORCE ROW LEVEL SECURITY")  # every office's
    op.execute("DELETE FROM password_links WHERE kind = 'confirm'")
    op.execute("ALTER TABLE password_links FORCE ROW LEVEL SECURITY")
    op.drop_constraint(op.f("ck_password_links_kind_known"), "password_links", type_="check")
    op.create_check_constraint(
        op.f("ck_password_links_kind_known"), "password_links", "kind IN ('invite', 'reset')"
    )
    op.drop_column("password_links", "tries")
    op.drop_column("password_links", "code_hash")
    op.drop_column("users", "email_confirmed_at")
