"""An SVG logo's PNG, for emails (A32).

Email programs don't show SVG images, so with an SVG logo the painel also uploads
a PNG it draws in the browser. `office_profiles.logo_png_file_id` points to it;
the app already may update the table.

Revision: 0020
Previous: 0019
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("office_profiles", sa.Column("logo_png_file_id", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("office_profiles", "logo_png_file_id")
