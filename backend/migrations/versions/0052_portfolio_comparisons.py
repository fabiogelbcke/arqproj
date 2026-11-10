"""A portfolio work's before-and-after comparisons (A46), 5 Nov 2026.

- `portfolio_photos.compare_photo_id`: on a "before" photo, the work's photo it
  is compared with (its "after"), shown together on a slider; the "after" photo
  is not shown on its own. Cleared if that photo is removed.
- `portfolio_photos.before_label`, `after_label`: the slider's words for its two
  sides, when not "Antes" and "Depois".

Revision: 0052
Previous: 0051
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0052"
down_revision: str | None = "0051"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("portfolio_photos", sa.Column("compare_photo_id", sa.Uuid(), nullable=True))
    op.add_column("portfolio_photos", sa.Column("before_label", sa.Text(), nullable=True))
    op.add_column("portfolio_photos", sa.Column("after_label", sa.Text(), nullable=True))
    # The office's own photos only: the reference carries the office.
    op.create_unique_constraint(
        "uq_portfolio_photos_tenant_id_id", "portfolio_photos", ["tenant_id", "id"]
    )
    op.create_foreign_key(
        "fk_portfolio_photos_compare",
        "portfolio_photos",
        "portfolio_photos",
        ["tenant_id", "compare_photo_id"],
        ["tenant_id", "id"],
        ondelete="SET NULL (compare_photo_id)",
    )
    # An "after" photo belongs to one comparison.
    op.create_index(
        "uq_portfolio_photos_compare_photo_id",
        "portfolio_photos",
        ["compare_photo_id"],
        unique=True,
        postgresql_where=sa.text("compare_photo_id IS NOT NULL"),
    )
    op.create_check_constraint(
        op.f("ck_portfolio_photos_compare_other"), "portfolio_photos", "compare_photo_id <> id"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_portfolio_photos_compare_other"), "portfolio_photos", type_="check")
    op.drop_index("uq_portfolio_photos_compare_photo_id", table_name="portfolio_photos")
    op.drop_constraint("fk_portfolio_photos_compare", "portfolio_photos", type_="foreignkey")
    op.drop_constraint("uq_portfolio_photos_tenant_id_id", "portfolio_photos", type_="unique")
    op.drop_column("portfolio_photos", "after_label")
    op.drop_column("portfolio_photos", "before_label")
    op.drop_column("portfolio_photos", "compare_photo_id")
