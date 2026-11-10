"""Meeting reminders and the notice settings (A48; schema changes approved by
Fabio, 10 Nov 2026).

- `meetings.reminded_day_for` and `reminded_soon_for`: the start each reminder
  was sent for, so it goes once per meeting time.
- `notice_settings`, one row for every office: the update batches' quiet period
  and maximum hold (A12), the reminder times, the days before an unanswered
  WhatsApp question is asked again (A47), and which news goes by WhatsApp. Written
  with the values the code held until now. The app reads it; the operator login
  reads and changes it, audited as its other changes to the whole site.

Revision: 0055
Previous: 0054
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision: str = "0055"
down_revision: str | None = "0054"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEWS = "'files', 'stages', 'project', 'meetings', 'reminders'"


def upgrade() -> None:
    for column in ("reminded_day_for", "reminded_soon_for"):
        op.add_column("meetings", sa.Column(column, sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "notice_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("quiet_minutes", sa.Integer(), nullable=False),
        sa.Column("hold_minutes", sa.Integer(), nullable=False),
        sa.Column("reminder_morning", sa.Time(), nullable=False),
        sa.Column("reminder_evening", sa.Time(), nullable=False),
        sa.Column("reminder_before_minutes", sa.Integer(), nullable=False),
        sa.Column("ask_again_days", sa.Integer(), nullable=False),
        sa.Column("whatsapp_news", ARRAY(sa.Text()), nullable=False),
        sa.CheckConstraint("id = 1", name=op.f("ck_notice_settings_one_row")),
        sa.CheckConstraint(
            "quiet_minutes BETWEEN 5 AND 120", name=op.f("ck_notice_settings_quiet_range")
        ),
        sa.CheckConstraint(
            "hold_minutes BETWEEN quiet_minutes AND 720",
            name=op.f("ck_notice_settings_hold_range"),
        ),
        sa.CheckConstraint(
            "reminder_before_minutes BETWEEN 5 AND 180",
            name=op.f("ck_notice_settings_before_range"),
        ),
        sa.CheckConstraint(
            "ask_again_days BETWEEN 1 AND 30", name=op.f("ck_notice_settings_ask_again_range")
        ),
        sa.CheckConstraint(
            "reminder_evening > reminder_morning",
            name=op.f("ck_notice_settings_evening_after_morning"),
        ),
        sa.CheckConstraint(
            f"whatsapp_news <@ ARRAY[{NEWS}]::text[]",
            name=op.f("ck_notice_settings_whatsapp_news_known"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notice_settings")),
    )
    op.execute(
        f"""
        INSERT INTO notice_settings (id, quiet_minutes, hold_minutes, reminder_morning,
            reminder_evening, reminder_before_minutes, ask_again_days, whatsapp_news)
        VALUES (1, 45, 120, '08:30', '18:00', 30, 3, ARRAY[{NEWS}])
        """
    )
    op.execute("""
        DO $$ BEGIN
            EXECUTE format('GRANT SELECT ON notice_settings TO %I', current_database() || '_app');
            EXECUTE format('GRANT SELECT, UPDATE ON notice_settings TO %I',
                           current_database() || '_operator');
        END $$
    """)


def downgrade() -> None:
    op.drop_table("notice_settings")
    for column in ("reminded_soon_for", "reminded_day_for"):
        op.drop_column("meetings", column)
