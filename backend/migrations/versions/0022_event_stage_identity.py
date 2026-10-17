"""A change record names its stage by identity too (A28).

`project_events.stage_id`: the stage a note or a stage advance is about. Stages
can be reordered or removed after the event; the page and the emails look up
where the stage is now, and drop the event if it is gone. Older events keep only
their position. No foreign key: a removed stage leaves the id pointing nowhere,
which is how its events are recognised.

Revision: 0022
Previous: 0021
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("project_events", sa.Column("stage_id", sa.Uuid(), nullable=True))


def downgrade() -> None:
    op.drop_column("project_events", "stage_id")
