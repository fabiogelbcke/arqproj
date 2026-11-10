"""Rules the code relies on, enforced by the database too (audit #210), 10 Nov 2026.

- One item per place in each order: portfolio sections, pieces, a piece's photos
  and videos, and the office's proposal services. Deferred, as stages' are, so a
  reorder or "every piece moves down a place" passes through duplicates.
- A portfolio video's file is registered once per office: removing one of two
  rows sharing a file trashed the file the other still played.
- A support account never has a password (A43).
- An email batch is closed (`closed_at`) exactly when sent or dropped; its last
  change never comes before its first; a delivery's attempts never go below 0.
- An office's own stage name fits the screens' limit (STAGE_TITLE_MAX, 80).

Rows already breaking a rule are put right first, every office's (the forced
policy lifted while the migration login copies them, as in 0053): duplicated
places are renumbered in their order, oldest first; a video registered twice
keeps its first row.

Revision: 0054
Previous: 0053
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0054"
down_revision: str | None = "0053"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (table, the order's owner): one item per place within each owner.
ORDERS = (
    ("portfolio_sections", "tenant_id"),
    ("portfolio_entries", "tenant_id"),
    ("portfolio_photos", "entry_id"),
    ("portfolio_videos", "entry_id"),
    ("proposal_service_presets", "tenant_id"),
)
TABLES = (
    *(table for table, _owner in ORDERS),
    "users",
    "notification_batches",
    "notification_deliveries",
    "project_stages",
)


def upgrade() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")

    # A file registered twice: the first row keeps it.
    op.execute(
        "DELETE FROM portfolio_videos AS later USING portfolio_videos AS first "
        "WHERE first.tenant_id = later.tenant_id AND first.file_id = later.file_id "
        "AND (first.created_at, first.id) < (later.created_at, later.id)"
    )
    # Owners with two items in one place: renumbered in their order, oldest first.
    for table, owner in ORDERS:
        op.execute(
            f"UPDATE {table} AS item SET position = renumbered.position "
            f"FROM (SELECT id, row_number() OVER (PARTITION BY {owner} "
            f"ORDER BY position, created_at, id) AS position FROM {table} "
            f"WHERE {owner} IN (SELECT {owner} FROM {table} "
            f"GROUP BY {owner}, position HAVING count(*) > 1)) AS renumbered "
            "WHERE item.id = renumbered.id AND item.position <> renumbered.position"
        )
    op.execute("UPDATE users SET password_hash = NULL WHERE support AND password_hash IS NOT NULL")
    op.execute(
        "UPDATE notification_batches SET closed_at = updated_at "
        "WHERE state IN ('sent', 'dropped') AND closed_at IS NULL"
    )
    op.execute(
        "UPDATE notification_batches SET closed_at = NULL "
        "WHERE state NOT IN ('sent', 'dropped') AND closed_at IS NOT NULL"
    )
    op.execute(
        "UPDATE notification_batches SET last_event_at = first_event_at "
        "WHERE last_event_at < first_event_at"
    )
    op.execute("UPDATE notification_deliveries SET attempts = 0 WHERE attempts < 0")
    op.execute("UPDATE project_stages SET title = left(title, 80) WHERE length(title) > 80")

    for table in TABLES:
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

    for table, owner in ORDERS:
        op.create_unique_constraint(
            f"uq_{table}_{owner}_position",
            table,
            [owner, "position"],
            deferrable=True,
            initially="DEFERRED",
        )
    op.create_unique_constraint(
        "uq_portfolio_videos_tenant_id_file_id", "portfolio_videos", ["tenant_id", "file_id"]
    )
    op.create_check_constraint(
        op.f("ck_users_support_without_password"),
        "users",
        "NOT support OR password_hash IS NULL",
    )
    op.create_check_constraint(
        op.f("ck_notification_batches_closed_when_done"),
        "notification_batches",
        "(state IN ('sent', 'dropped')) = (closed_at IS NOT NULL)",
    )
    op.create_check_constraint(
        op.f("ck_notification_batches_events_in_order"),
        "notification_batches",
        "last_event_at >= first_event_at",
    )
    op.create_check_constraint(
        op.f("ck_notification_deliveries_attempts_not_negative"),
        "notification_deliveries",
        "attempts >= 0",
    )
    op.create_check_constraint(
        op.f("ck_project_stages_title_length"), "project_stages", "length(title) <= 80"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_project_stages_title_length"), "project_stages", type_="check")
    op.drop_constraint(
        op.f("ck_notification_deliveries_attempts_not_negative"),
        "notification_deliveries",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_notification_batches_events_in_order"), "notification_batches", type_="check"
    )
    op.drop_constraint(
        op.f("ck_notification_batches_closed_when_done"), "notification_batches", type_="check"
    )
    op.drop_constraint(op.f("ck_users_support_without_password"), "users", type_="check")
    op.drop_constraint("uq_portfolio_videos_tenant_id_file_id", "portfolio_videos", type_="unique")
    for table, owner in reversed(ORDERS):
        op.drop_constraint(f"uq_{table}_{owner}_position", table, type_="unique")
