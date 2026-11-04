"""A portfolio work's sheet of details (A45), 4 Nov 2026.

- `portfolio_details`: each line of a work's sheet, in order: one of the built-in
  details a project has (`key`, typed and labelled as the project page's), or one
  with a label of the office's own (`label`, text only). A built-in row's value
  type is its detail type's, and exactly the value column of that type is filled.
- `portfolio_entries` loses `area` and `team`: each work's area becomes its
  "Área construída" line and its team its "Responsável" line, in that order; the
  downgrade puts the first of each back.

Isolated per office like every office table; the app reads and changes the
rows, and the operator role deletes them with the office (A38).

Revision: 0051
Previous: 0050
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0051"
down_revision: str | None = "0050"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VALUE_MATCHES_TYPE = (
    "(value_type = 'text' AND value_text IS NOT NULL AND value_number IS NULL "
    "AND value_date IS NULL) OR (value_type = 'area' AND value_text IS NULL "
    "AND value_number IS NOT NULL AND value_date IS NULL) OR (value_type = 'date' "
    "AND value_text IS NULL AND value_number IS NULL AND value_date IS NOT NULL)"
)


def upgrade() -> None:
    op.create_table(
        "portfolio_details",
        sa.Column("entry_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("key", sa.Text(), nullable=True),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("value_type", sa.Text(), nullable=False),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("value_number", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("value_date", sa.Date(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "tenant_id", sa.Uuid(), server_default=sa.text("current_tenant_id()"), nullable=False
        ),
        sa.CheckConstraint(
            "(key IS NOT NULL AND label IS NULL) "
            "OR (key IS NULL AND label IS NOT NULL AND value_type = 'text')",
            name=op.f("ck_portfolio_details_built_in_or_own"),
        ),
        sa.CheckConstraint(
            "label IS NULL OR length(btrim(label)) BETWEEN 1 AND 40",
            name=op.f("ck_portfolio_details_label_length"),
        ),
        sa.CheckConstraint(
            "value_number IS NULL OR value_number >= 0",
            name=op.f("ck_portfolio_details_number_not_negative"),
        ),
        sa.CheckConstraint("position >= 1", name=op.f("ck_portfolio_details_position_positive")),
        sa.CheckConstraint(
            "value_text IS NULL OR length(btrim(value_text)) > 0",
            name=op.f("ck_portfolio_details_text_not_blank"),
        ),
        sa.CheckConstraint(
            "value_text IS NULL OR length(value_text) <= 200",
            name=op.f("ck_portfolio_details_text_length"),
        ),
        sa.CheckConstraint(
            VALUE_MATCHES_TYPE, name=op.f("ck_portfolio_details_value_matches_type")
        ),
        sa.CheckConstraint(
            "value_type IN ('text', 'area', 'date')",
            name=op.f("ck_portfolio_details_value_type_known"),
        ),
        sa.ForeignKeyConstraint(
            ["key", "value_type"],
            ["detail_types.key", "detail_types.value_type"],
            name="fk_portfolio_details_detail_type",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "entry_id"],
            ["portfolio_entries.tenant_id", "portfolio_entries.id"],
            name="fk_portfolio_details_entry",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_portfolio_details_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portfolio_details")),
        sa.UniqueConstraint("entry_id", "key", name="uq_portfolio_details_entry_id_key"),
        sa.UniqueConstraint(
            "entry_id",
            "position",
            name="uq_portfolio_details_entry_id_position",
            deferrable=True,
            initially="DEFERRED",
        ),
    )
    op.create_index(
        op.f("ix_portfolio_details_entry_id"), "portfolio_details", ["entry_id"], unique=False
    )
    op.create_index(
        op.f("ix_portfolio_details_tenant_id"), "portfolio_details", ["tenant_id"], unique=False
    )
    # Isolated per office, as every office table (0001's policy and the operator's
    # delete right, as 0049 gave the other portfolio tables).
    op.execute("ALTER TABLE portfolio_details ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE portfolio_details FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON portfolio_details "
        "USING (tenant_id = current_tenant_id()) WITH CHECK (tenant_id = current_tenant_id())"
    )
    op.execute(
        """
        DO $$
        DECLARE app_role text := current_database() || '_app';
                operator_role text := current_database() || '_operator';
        BEGIN
            EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON portfolio_details TO %I',
                           app_role);
            EXECUTE format('GRANT SELECT, DELETE ON portfolio_details TO %I', operator_role);
        END $$
        """
    )
    # Each work's area and team become the first lines of its sheet: every
    # office's, so with the forced policy lifted while the migration login (the
    # tables' owner, no superuser on Cloud SQL) copies them (snippets.py, 0008).
    op.execute("ALTER TABLE portfolio_entries NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE portfolio_details NO FORCE ROW LEVEL SECURITY")
    op.execute(
        "INSERT INTO portfolio_details "
        "(tenant_id, entry_id, position, key, value_type, value_number) "
        "SELECT tenant_id, id, 1, 'built_area', 'area', area FROM portfolio_entries "
        "WHERE area IS NOT NULL"
    )
    op.execute(
        "INSERT INTO portfolio_details "
        "(tenant_id, entry_id, position, key, value_type, value_text) "
        "SELECT tenant_id, id, CASE WHEN area IS NULL THEN 1 ELSE 2 END, "
        "'responsible', 'text', team FROM portfolio_entries WHERE length(btrim(team)) > 0"
    )
    op.execute("ALTER TABLE portfolio_details FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE portfolio_entries FORCE ROW LEVEL SECURITY")
    op.drop_constraint(op.f("ck_portfolio_entries_area_range"), "portfolio_entries", type_="check")
    op.drop_constraint(op.f("ck_portfolio_entries_team_length"), "portfolio_entries", type_="check")
    op.drop_column("portfolio_entries", "team")
    op.drop_column("portfolio_entries", "area")


def downgrade() -> None:
    op.add_column(
        "portfolio_entries",
        sa.Column("area", sa.Numeric(precision=12, scale=2), nullable=True),
    )
    op.add_column(
        "portfolio_entries",
        sa.Column("team", sa.Text(), server_default=sa.text("''"), nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_portfolio_entries_area_range"), "portfolio_entries", "area > 0 AND area < 10000000"
    )
    op.create_check_constraint(
        op.f("ck_portfolio_entries_team_length"), "portfolio_entries", "length(team) <= 200"
    )
    op.execute("ALTER TABLE portfolio_entries NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE portfolio_details NO FORCE ROW LEVEL SECURITY")
    op.execute(
        "UPDATE portfolio_entries e SET area = d.value_number FROM portfolio_details d "
        "WHERE d.entry_id = e.id AND d.key = 'built_area' "
        "AND d.value_number > 0 AND d.value_number < 10000000"  # what the old column takes
    )
    op.execute(
        "UPDATE portfolio_entries e SET team = left(d.value_text, 200) FROM portfolio_details d "
        "WHERE d.entry_id = e.id AND d.key = 'responsible'"
    )
    op.execute("ALTER TABLE portfolio_entries FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY tenant_isolation ON portfolio_details")
    op.drop_index(op.f("ix_portfolio_details_tenant_id"), table_name="portfolio_details")
    op.drop_index(op.f("ix_portfolio_details_entry_id"), table_name="portfolio_details")
    op.drop_table("portfolio_details")
