"""The maintenance pass's last results (plan section 4: "record a last-success
time so failures are visible").

One row for the whole service, not an office's, so no tenant isolation: it holds
when the pass last ran, when it last ran to the end, and that pass's report. The
app reads, adds and updates it.

Revision: 0021
Previous: 0020
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "maintenance_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_report", JSONB(), nullable=False),
        sa.CheckConstraint("id = 1", name=op.f("ck_maintenance_runs_one_row")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_maintenance_runs")),
    )
    op.execute(
        "DO $$ BEGIN EXECUTE format("
        "'GRANT SELECT, INSERT, UPDATE ON maintenance_runs TO %I', current_database() || '_app'"
        "); END $$"
    )


def downgrade() -> None:
    op.drop_table("maintenance_runs")
