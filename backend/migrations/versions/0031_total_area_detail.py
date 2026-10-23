"""A built-in detail "Área total" (A27; Fabio, 23 Oct 2026).

Data only: one row in `detail_types`, an area like the site's and the built
area, listed right after them (the dates and the lead architect move down one).

Revision: 0031
Previous: 0030
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE detail_types SET position = position + 1 "
        "WHERE key IN ('start_date', 'expected_delivery', 'responsible')"
    )
    op.execute(
        "INSERT INTO detail_types (key, value_type, position, labels) VALUES "
        '(\'total_area\', \'area\', 5, \'{"pt-BR": "Área total", "en": "Total area"}\'::jsonb)'
    )


def downgrade() -> None:
    op.execute("DELETE FROM project_details WHERE key = 'total_area'")
    op.execute("DELETE FROM detail_types WHERE key = 'total_area'")
    op.execute(
        "UPDATE detail_types SET position = position - 1 "
        "WHERE key IN ('start_date', 'expected_delivery', 'responsible')"
    )
