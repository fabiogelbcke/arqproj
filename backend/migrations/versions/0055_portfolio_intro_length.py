"""The portfolio's opening text ("Apresentação") takes up to 1000 characters, 600
until now (A45; Fabio, 12 Nov 2026).

Revision: 0055
Previous: 0054
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0055"
down_revision: str | None = "0054"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_portfolios_intro_length"), "portfolios", type_="check")
    op.create_check_constraint(
        op.f("ck_portfolios_intro_length"), "portfolios", "length(intro) <= 1000"
    )


def downgrade() -> None:
    # A text written at the new length is cut to the old one, never refused. The
    # table forces row-level security (0049) and a migration has no tenant, so
    # the rule is lifted for the update and put back.
    op.execute("ALTER TABLE portfolios NO FORCE ROW LEVEL SECURITY")
    op.execute("UPDATE portfolios SET intro = left(intro, 600) WHERE length(intro) > 600")
    op.execute("ALTER TABLE portfolios FORCE ROW LEVEL SECURITY")
    op.drop_constraint(op.f("ck_portfolios_intro_length"), "portfolios", type_="check")
    op.create_check_constraint(
        op.f("ck_portfolios_intro_length"), "portfolios", "length(intro) <= 600"
    )
