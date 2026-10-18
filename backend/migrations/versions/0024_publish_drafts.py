"""No drafts for now (A35): projects still waiting as drafts are published. The
`draft` status stays allowed, unused, so drafts can return without a schema
change. Data only.

Revision: 0024
Previous: 0023
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Every office's rows: the forced isolation policy would hide them from the
    # migration login (backend/migrations/snippets.py, "a backfill").
    op.execute("ALTER TABLE projects NO FORCE ROW LEVEL SECURITY")
    op.execute("UPDATE projects SET status = 'active' WHERE status = 'draft'")
    # An archived draft, if restored, comes back published.
    op.execute("UPDATE projects SET archived_from = 'active' WHERE archived_from = 'draft'")
    op.execute("ALTER TABLE projects FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    pass  # which projects were drafts isn't kept; they stay published
