"""Support access (A43, 30 Oct 2026): an operator enters an office as its owner
or a member.

- `users.support`: the office's hidden "Suporte Unio" accounts, one per role.
  They have no password and are left out of the team, counts and notices.
- `password_links.kind` gains `support`: the one-time hand-off that signs the
  operator's browser in to the office's address as one of them.

The app already may insert users and password links; no grant changes.

Revision: 0044
Previous: 0043
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0044"
down_revision: str | None = "0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("support", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.drop_constraint(op.f("ck_password_links_kind_known"), "password_links", type_="check")
    op.create_check_constraint(
        op.f("ck_password_links_kind_known"),
        "password_links",
        "kind IN ('invite', 'reset', 'confirm', 'support')",
    )


def downgrade() -> None:
    # Every office's support accounts go, and with them their links and sessions.
    op.execute("ALTER TABLE password_links NO FORCE ROW LEVEL SECURITY")
    op.execute("DELETE FROM password_links WHERE kind = 'support'")
    op.execute("ALTER TABLE password_links FORCE ROW LEVEL SECURITY")
    op.drop_constraint(op.f("ck_password_links_kind_known"), "password_links", type_="check")
    op.create_check_constraint(
        op.f("ck_password_links_kind_known"),
        "password_links",
        "kind IN ('invite', 'reset', 'confirm')",
    )
    # What they made stays, its maker unknown (`created_by` allows that).
    for table in ("share_links", "proposals", "join_links", "users"):
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
    for table in ("share_links", "proposals", "join_links"):
        op.execute(
            f"UPDATE {table} SET created_by = NULL "
            "WHERE created_by IN (SELECT id FROM users WHERE support)"
        )
    op.execute("DELETE FROM users WHERE support")
    for table in ("share_links", "proposals", "join_links", "users"):
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.drop_column("users", "support")
