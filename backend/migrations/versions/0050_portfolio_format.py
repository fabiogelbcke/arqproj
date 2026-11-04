"""A portfolio's format and its images' pixel sizes (A45), 4 Nov 2026.

- `portfolios.format`: `works` (one landscape cover per work, a carousel and a
  work's page opening on its cover) or `feed` (every image in its own shape, as
  the social networks show them), for an office whose material was made for its
  posts, stories and reels.
- `portfolio_photos` and `portfolio_videos`: the photo's and the poster's width
  and height in pixels, read when the file is added, so the page lays an image
  out at its own shape before it loads. Null for files added before this, and
  for a file the server couldn't read.

Revision: 0050
Previous: 0049
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0050"
down_revision: str | None = "0049"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SIZED = ("portfolio_photos", "portfolio_videos")


def upgrade() -> None:
    op.add_column(
        "portfolios",
        sa.Column("format", sa.Text(), server_default=sa.text("'works'"), nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_portfolios_format_known"), "portfolios", "format IN ('works', 'feed')"
    )
    for table in SIZED:
        op.add_column(table, sa.Column("width", sa.Integer(), nullable=True))
        op.add_column(table, sa.Column("height", sa.Integer(), nullable=True))
        op.create_check_constraint(
            op.f(f"ck_{table}_size_positive"), table, "width > 0 AND height > 0"
        )


def downgrade() -> None:
    for table in reversed(SIZED):
        op.drop_constraint(op.f(f"ck_{table}_size_positive"), table, type_="check")
        op.drop_column(table, "height")
        op.drop_column(table, "width")
    op.drop_constraint(op.f("ck_portfolios_format_known"), "portfolios", type_="check")
    op.drop_column("portfolios", "format")
