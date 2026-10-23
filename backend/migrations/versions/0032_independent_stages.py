"""Stages complete on their own, in any order (Fabio, 23 Oct 2026, for review).

Each stage gets `completed_at`: set when staff mark it as completed, cleared when
they reopen it. Filled from the old progress: the stages before a project's
current one are completed, and all of a completed project's. `projects.
current_position` stays, unused, until the change is confirmed. A new event,
`stage_completed`, tells the client (A28, A32); `stage_advanced` stays for the
events already recorded.

Revision: 0032
Previous: 0031
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS_BEFORE = (
    "'file_published', 'stage_advanced', 'project_completed', 'meeting_scheduled', "
    "'meeting_changed', 'meeting_cleared', 'note_changed'"
)
# In the enum's order (EventKind), as the models write the check.
KINDS_AFTER = (
    "'file_published', 'stage_advanced', 'stage_completed', 'project_completed', "
    "'meeting_scheduled', 'meeting_changed', 'meeting_cleared', 'note_changed'"
)


def _grant(statement: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            EXECUTE format('{statement}', current_database() || '_app');
        END $$
        """
    )


def upgrade() -> None:
    op.add_column("project_stages", sa.Column("completed_at", sa.DateTime(timezone=True)))
    # Every office's rows: the forced isolation policy would hide them from the
    # migration login (backend/migrations/snippets.py, "a backfill").
    op.execute("ALTER TABLE projects NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE project_stages NO FORCE ROW LEVEL SECURITY")
    op.execute(
        "UPDATE project_stages s SET completed_at = now() FROM projects p "
        "WHERE p.id = s.project_id AND (p.status = 'completed' "
        "OR (p.current_position IS NOT NULL AND s.position < p.current_position))"
    )
    op.execute("ALTER TABLE project_stages FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE projects FORCE ROW LEVEL SECURITY")
    op.drop_constraint(op.f("ck_project_events_kind_known"), "project_events")
    op.create_check_constraint(
        op.f("ck_project_events_kind_known"), "project_events", f"kind IN ({KINDS_AFTER})"
    )
    _grant("GRANT UPDATE (completed_at) ON project_stages TO %I")


def downgrade() -> None:
    _grant("REVOKE UPDATE (completed_at) ON project_stages FROM %I")
    op.execute("ALTER TABLE project_events NO FORCE ROW LEVEL SECURITY")  # every office's
    op.execute("DELETE FROM project_events WHERE kind = 'stage_completed'")
    op.execute("ALTER TABLE project_events FORCE ROW LEVEL SECURITY")
    op.drop_constraint(op.f("ck_project_events_kind_known"), "project_events")
    op.create_check_constraint(
        op.f("ck_project_events_kind_known"), "project_events", f"kind IN ({KINDS_BEFORE})"
    )
    op.drop_column("project_stages", "completed_at")
