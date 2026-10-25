"""Reopening a stage tells the client too (Fabio, 25 Oct 2026): a new event,
`stage_reopened` (A28, A32).

Revision: 0033
Previous: 0032
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS_BEFORE = (
    "'file_published', 'stage_advanced', 'stage_completed', 'project_completed', "
    "'meeting_scheduled', 'meeting_changed', 'meeting_cleared', 'note_changed'"
)
# In the enum's order (EventKind), as the models write the check.
KINDS_AFTER = (
    "'file_published', 'stage_advanced', 'stage_completed', 'stage_reopened', "
    "'project_completed', 'meeting_scheduled', 'meeting_changed', 'meeting_cleared', "
    "'note_changed'"
)


def upgrade() -> None:
    op.drop_constraint(op.f("ck_project_events_kind_known"), "project_events")
    op.create_check_constraint(
        op.f("ck_project_events_kind_known"), "project_events", f"kind IN ({KINDS_AFTER})"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE project_events NO FORCE ROW LEVEL SECURITY")  # every office's
    op.execute("DELETE FROM project_events WHERE kind = 'stage_reopened'")
    op.execute("ALTER TABLE project_events FORCE ROW LEVEL SECURITY")
    op.drop_constraint(op.f("ck_project_events_kind_known"), "project_events")
    op.create_check_constraint(
        op.f("ck_project_events_kind_known"), "project_events", f"kind IN ({KINDS_BEFORE})"
    )
