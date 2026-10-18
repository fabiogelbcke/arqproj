"""Project addresses can't be `privacidade` or `termos`: Unio's privacy policy and
terms of use are at those paths on every address (A33).

Revision: 0023
Previous: 0022
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BEFORE = "'painel', 'api', 'static', 'assets', 'health', 'healthz', 'statusz'"
AFTER = BEFORE + ", 'privacidade', 'termos'"


def _reserve(names: str) -> None:
    name = op.f("ck_project_slugs_slug_not_reserved")
    op.drop_constraint(name, "project_slugs", type_="check")
    op.create_check_constraint(name, "project_slugs", f"slug NOT IN ({names})")


def upgrade() -> None:
    _reserve(AFTER)


def downgrade() -> None:
    _reserve(BEFORE)
