"""Comments on a project's files and stages, by clients and staff (A49), 10 Nov 2026.

- `comments`: one comment, on a stage (`stage_id`, gone with the stage) or on a
  file (`item_id`, its identity in storage; `item_name`, its name then), by a
  client (a typed name) or a staff account. `alert_batch`, `alert_tried_at` and
  `staff_notified_at`: the email to staff a client's is in, when it was first
  tried, and when it went to every address.
- `project_events.kind` takes `office_commented`: a staff comment is client news
  (A28, A32).

Revision: 0056
Previous: 0055
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0056"
down_revision: str | None = "0055"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS_BEFORE = (
    "'file_published', 'stage_advanced', 'stage_completed', 'stage_reopened', "
    "'project_completed', 'meeting_scheduled', 'meeting_changed', 'meeting_cleared', "
    "'note_changed'"
)
# In the enum's order (EventKind), as the models write the check.
KINDS_AFTER = (
    "'file_published', 'stage_advanced', 'stage_completed', 'stage_reopened', "
    "'project_completed', 'meeting_scheduled', 'meeting_changed', 'meeting_cleared', "
    "'note_changed', 'office_commented'"
)


def upgrade() -> None:
    op.create_table(
        "comments",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("stage_id", sa.Uuid(), nullable=True),
        sa.Column("item_id", sa.Text(), nullable=True),
        sa.Column("item_name", sa.Text(), nullable=True),
        sa.Column("author", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("author_name", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("alert_batch", sa.Uuid(), nullable=True),
        sa.Column("alert_tried_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("staff_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id", sa.Uuid(), server_default=sa.text("current_tenant_id()"), nullable=False
        ),
        sa.CheckConstraint("author IN ('client', 'staff')", name=op.f("ck_comments_author_known")),
        sa.CheckConstraint(
            "(stage_id IS NULL) <> (item_id IS NULL)", name=op.f("ck_comments_stage_or_file")
        ),
        sa.CheckConstraint(
            "length(btrim(body)) BETWEEN 1 AND 2000", name=op.f("ck_comments_body_length")
        ),
        sa.CheckConstraint(
            "length(btrim(author_name)) BETWEEN 1 AND 80",
            name=op.f("ck_comments_author_name_length"),
        ),
        sa.CheckConstraint(
            "author = 'staff' OR user_id IS NULL", name=op.f("ck_comments_client_has_no_account")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.id"],
            name="fk_comments_project",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_comments_user",
            ondelete="SET NULL (user_id)",
        ),
        sa.ForeignKeyConstraint(
            ["stage_id"], ["project_stages.id"], name="fk_comments_stage", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_comments_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_comments")),
    )
    op.create_index(op.f("ix_comments_tenant_id"), "comments", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_comments_stage_id"), "comments", ["stage_id"], unique=False)
    op.create_index(
        "ix_comments_project_id_created_at", "comments", ["project_id", "created_at"], unique=False
    )
    # Isolated per office, as every office table (0001's policy and the operator's
    # delete right, as 0049 gave the portfolio's tables). The app adds comments and
    # never rewrites one: it only marks one removed, or its staff emailed.
    op.execute("ALTER TABLE comments ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE comments FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON comments "
        "USING (tenant_id = current_tenant_id()) WITH CHECK (tenant_id = current_tenant_id())"
    )
    op.execute(
        """
        DO $$
        DECLARE app_role text := current_database() || '_app';
                operator_role text := current_database() || '_operator';
        BEGIN
            EXECUTE format('GRANT SELECT, INSERT ON comments TO %I', app_role);
            EXECUTE format('GRANT UPDATE (removed_at, alert_batch, alert_tried_at, '
                           'staff_notified_at) '
                           'ON comments TO %I', app_role);
            EXECUTE format('GRANT SELECT, DELETE ON comments TO %I', operator_role);
        END $$
        """
    )
    op.drop_constraint(op.f("ck_project_events_kind_known"), "project_events")
    op.create_check_constraint(
        op.f("ck_project_events_kind_known"), "project_events", f"kind IN ({KINDS_AFTER})"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE project_events NO FORCE ROW LEVEL SECURITY")  # every office's
    op.execute("DELETE FROM project_events WHERE kind = 'office_commented'")
    op.execute("ALTER TABLE project_events FORCE ROW LEVEL SECURITY")
    op.drop_constraint(op.f("ck_project_events_kind_known"), "project_events")
    op.create_check_constraint(
        op.f("ck_project_events_kind_known"), "project_events", f"kind IN ({KINDS_BEFORE})"
    )
    op.drop_index("ix_comments_project_id_created_at", table_name="comments")
    op.drop_index(op.f("ix_comments_stage_id"), table_name="comments")
    op.drop_index(op.f("ix_comments_tenant_id"), table_name="comments")
    op.drop_table("comments")
