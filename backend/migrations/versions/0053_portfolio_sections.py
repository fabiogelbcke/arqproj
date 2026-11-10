"""The portfolio in sections, every image a piece of it (A45), 9 Nov 2026.

- `portfolio_sections`: an office's sections of its Portfólio tab, in order, each
  one of the site's project types or a name of the office's own, with the slug
  the page's address names it by (`/?tipo=…`). The menu of the public page.
- `portfolio_entries.section_id` replaces `project_type`: a piece is in one
  section or none. Every type an office's works used becomes a section of it,
  in the types' order, and its works move there.
- `portfolio_entries.title` may be empty: a piece needs no title.
- `portfolio_entries.status` is dropped: not asked or shown since 5 Nov 2026.

Revision: 0053
Previous: 0052
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0053"
down_revision: str | None = "0052"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "portfolio_sections",
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("project_type", sa.Text(), nullable=True),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id", sa.Uuid(), server_default=sa.text("current_tenant_id()"), nullable=False
        ),
        sa.CheckConstraint(
            "label IS NULL OR length(btrim(label)) BETWEEN 1 AND 40",
            name=op.f("ck_portfolio_sections_label_length"),
        ),
        sa.CheckConstraint("position >= 1", name=op.f("ck_portfolio_sections_position_positive")),
        sa.CheckConstraint(
            "slug ~ '^[a-z0-9_]+(-[a-z0-9_]+)*$'", name=op.f("ck_portfolio_sections_slug_shape")
        ),
        sa.CheckConstraint(
            "(project_type IS NOT NULL AND label IS NULL) "
            "OR (project_type IS NULL AND label IS NOT NULL)",
            name=op.f("ck_portfolio_sections_type_or_own"),
        ),
        sa.ForeignKeyConstraint(
            ["project_type"], ["project_types.key"], name="fk_portfolio_sections_project_type"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_portfolio_sections_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portfolio_sections")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_portfolio_sections_tenant_id_id"),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_portfolio_sections_tenant_id_slug"),
    )
    op.create_index(
        op.f("ix_portfolio_sections_tenant_id"), "portfolio_sections", ["tenant_id"], unique=False
    )
    op.create_index(
        "uq_portfolio_sections_project_type",
        "portfolio_sections",
        ["tenant_id", "project_type"],
        unique=True,
        postgresql_where=sa.text("project_type IS NOT NULL"),
    )
    # Isolated per office, as every office table (0001's policy and the operator's
    # delete right, as 0049 gave the other portfolio tables), with updated_at kept.
    op.execute("ALTER TABLE portfolio_sections ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE portfolio_sections FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON portfolio_sections "
        "USING (tenant_id = current_tenant_id()) WITH CHECK (tenant_id = current_tenant_id())"
    )
    op.execute(
        "CREATE TRIGGER portfolio_sections_set_updated_at BEFORE UPDATE ON portfolio_sections "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.execute(
        """
        DO $$
        DECLARE app_role text := current_database() || '_app';
                operator_role text := current_database() || '_operator';
        BEGIN
            EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON portfolio_sections TO %I',
                           app_role);
            EXECUTE format('GRANT SELECT, DELETE ON portfolio_sections TO %I', operator_role);
        END $$
        """
    )

    op.add_column("portfolio_entries", sa.Column("section_id", sa.Uuid(), nullable=True))
    op.create_index(
        op.f("ix_portfolio_entries_section_id"), "portfolio_entries", ["section_id"], unique=False
    )
    op.create_foreign_key(
        "fk_portfolio_entries_section",
        "portfolio_entries",
        "portfolio_sections",
        ["tenant_id", "section_id"],
        ["tenant_id", "id"],
        ondelete="SET NULL (section_id)",
    )
    # Every type an office's works used becomes a section of that office, in
    # the types' order, and the works move there: every office's rows, so with
    # the forced policy lifted while the migration login (the tables' owner, no
    # superuser on Cloud SQL) copies them (snippets.py, 0008, 0051).
    op.execute("ALTER TABLE portfolio_entries NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE portfolio_sections NO FORCE ROW LEVEL SECURITY")
    op.execute(
        "INSERT INTO portfolio_sections (tenant_id, position, project_type, slug) "
        "SELECT used.tenant_id, "
        "row_number() OVER (PARTITION BY used.tenant_id ORDER BY kind.position, kind.key), "
        "used.project_type, used.project_type "
        "FROM (SELECT DISTINCT tenant_id, project_type FROM portfolio_entries "
        "WHERE project_type IS NOT NULL) AS used "
        "JOIN project_types AS kind ON kind.key = used.project_type"
    )
    op.execute(
        "UPDATE portfolio_entries AS entry SET section_id = section.id "
        "FROM portfolio_sections AS section "
        "WHERE section.tenant_id = entry.tenant_id "
        "AND section.project_type = entry.project_type"
    )
    op.execute("ALTER TABLE portfolio_sections FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE portfolio_entries FORCE ROW LEVEL SECURITY")

    op.drop_constraint("fk_portfolio_entries_project_type", "portfolio_entries", type_="foreignkey")
    op.drop_column("portfolio_entries", "project_type")
    op.drop_constraint(
        op.f("ck_portfolio_entries_status_known"), "portfolio_entries", type_="check"
    )
    op.drop_column("portfolio_entries", "status")
    op.drop_constraint(
        op.f("ck_portfolio_entries_title_length"), "portfolio_entries", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_portfolio_entries_title_length"), "portfolio_entries", "length(title) <= 80"
    )


def downgrade() -> None:
    op.add_column("portfolio_entries", sa.Column("project_type", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_portfolio_entries_project_type",
        "portfolio_entries",
        "project_types",
        ["project_type"],
        ["key"],
    )
    op.add_column("portfolio_entries", sa.Column("status", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_portfolio_entries_status_known"),
        "portfolio_entries",
        "status IN ('completed', 'in_progress')",
    )
    # A piece's type back from its section (an own section has none); a title
    # where there was none, since the old table demanded one.
    op.execute("ALTER TABLE portfolio_entries NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE portfolio_sections NO FORCE ROW LEVEL SECURITY")
    op.execute(
        "UPDATE portfolio_entries AS entry SET project_type = section.project_type "
        "FROM portfolio_sections AS section WHERE section.id = entry.section_id"
    )
    op.execute("UPDATE portfolio_entries SET title = 'Sem título' WHERE length(btrim(title)) = 0")
    op.execute("ALTER TABLE portfolio_sections FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE portfolio_entries FORCE ROW LEVEL SECURITY")
    op.drop_constraint(
        op.f("ck_portfolio_entries_title_length"), "portfolio_entries", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_portfolio_entries_title_length"),
        "portfolio_entries",
        "length(btrim(title)) BETWEEN 1 AND 80",
    )
    op.drop_constraint("fk_portfolio_entries_section", "portfolio_entries", type_="foreignkey")
    op.drop_index(op.f("ix_portfolio_entries_section_id"), table_name="portfolio_entries")
    op.drop_column("portfolio_entries", "section_id")
    op.drop_index("uq_portfolio_sections_project_type", table_name="portfolio_sections")
    op.drop_index(op.f("ix_portfolio_sections_tenant_id"), table_name="portfolio_sections")
    op.drop_table("portfolio_sections")
