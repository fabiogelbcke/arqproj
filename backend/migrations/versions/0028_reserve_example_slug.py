"""Project addresses can't be `tour-projeto`: the example project is at that path
on every office's address (plan section 16, "Onboarding help").

Revision: 0028
Previous: 0027
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BEFORE = (
    "'painel', 'api', 'static', 'assets', 'health', 'healthz', 'statusz', 'privacidade', 'termos'"
)
AFTER = BEFORE + ", 'tour-projeto'"


def _reserve(names: str) -> None:
    name = op.f("ck_project_slugs_slug_not_reserved")
    op.drop_constraint(name, "project_slugs", type_="check")
    op.create_check_constraint(name, "project_slugs", f"slug NOT IN ({names})")


def upgrade() -> None:
    _reserve(AFTER)


def downgrade() -> None:
    _reserve(BEFORE)
