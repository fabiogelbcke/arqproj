"""A logo for dark mode (plan section 16: "light/dark logo").

`office_profiles.logo_dark_file_id` and `logo_dark_type`: none means the pages
show the usual logo in dark mode too. The app already may update the table.

Revision: 0025
Previous: 0024
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("office_profiles", sa.Column("logo_dark_file_id", sa.Text(), nullable=True))
    op.add_column("office_profiles", sa.Column("logo_dark_type", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_office_profiles_logo_dark_type_known"),
        "office_profiles",
        "logo_dark_type IN ('image/png', 'image/jpeg', 'image/webp', 'image/svg+xml')",
    )
    op.create_check_constraint(
        op.f("ck_office_profiles_logo_dark_complete"),
        "office_profiles",
        "(logo_dark_file_id IS NULL) = (logo_dark_type IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_office_profiles_logo_dark_complete"), "office_profiles")
    op.drop_constraint(op.f("ck_office_profiles_logo_dark_type_known"), "office_profiles")
    op.drop_column("office_profiles", "logo_dark_type")
    op.drop_column("office_profiles", "logo_dark_file_id")
