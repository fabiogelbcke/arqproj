"""Tenants' locale must be a language the site is translated into.

Revision: 0004
Previous: 0003
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_check_constraint(
        op.f("ck_tenants_locale_known"), "tenants", "locale IN ('pt-BR', 'en')"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_tenants_locale_known"), "tenants", type_="check")
