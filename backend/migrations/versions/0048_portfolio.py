"""The office's portfolio (behind the `portfolio` feature, A40), 31 Oct 2026.

- `portfolios`: one row per office, whether its address shows the portfolio at
  `/`, the page's opening text, the office's social network profiles, and the
  storage folder holding the photos.
- `portfolio_entries`: each work shown, in order, with its type (the public page's
  menu), area, status, team and photo credits, optionally drawn from a project.
- `portfolio_photos`: each entry's photos, in order (copies in the office's storage).
- `portfolio_videos`: each entry's videos, in order, with a frame shown before
  they play (both in the office's storage).

All four are isolated per office like every office table; the app reads and
changes them, and the operator role deletes them with the office (A38).

Revision: 0044
Previous: 0043
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0048"
down_revision: str | None = "0047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("portfolios", "portfolio_entries", "portfolio_photos", "portfolio_videos")


def upgrade() -> None:
    op.create_table(
        "portfolios",
        sa.Column("published", sa.Boolean(), nullable=False),
        sa.Column("intro", sa.Text(), nullable=False),
        sa.Column(
            "links",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("folder_id", sa.Text(), nullable=True),
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
        sa.CheckConstraint("length(intro) <= 600", name=op.f("ck_portfolios_intro_length")),
        sa.CheckConstraint(
            "jsonb_typeof(links) = 'object'", name=op.f("ck_portfolios_links_object")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_portfolios_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portfolios")),
        sa.UniqueConstraint("tenant_id", name="uq_portfolios_tenant_id"),
    )
    op.create_index(op.f("ix_portfolios_tenant_id"), "portfolios", ["tenant_id"], unique=False)
    op.create_table(
        "portfolio_entries",
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("place", sa.Text(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("project_type", sa.Text(), nullable=True),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("area", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("status", sa.Text(), nullable=True),
        sa.Column("team", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("credits", sa.Text(), server_default=sa.text("''"), nullable=False),
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
            "area > 0 AND area < 10000000", name=op.f("ck_portfolio_entries_area_range")
        ),
        sa.CheckConstraint(
            "status IN ('completed', 'in_progress')", name=op.f("ck_portfolio_entries_status_known")
        ),
        sa.CheckConstraint("length(team) <= 200", name=op.f("ck_portfolio_entries_team_length")),
        sa.CheckConstraint(
            "length(credits) <= 120", name=op.f("ck_portfolio_entries_credits_length")
        ),
        sa.CheckConstraint(
            "length(btrim(title)) BETWEEN 1 AND 80", name=op.f("ck_portfolio_entries_title_length")
        ),
        sa.CheckConstraint(
            "length(description) <= 2000", name=op.f("ck_portfolio_entries_description_length")
        ),
        sa.CheckConstraint("length(place) <= 80", name=op.f("ck_portfolio_entries_place_length")),
        sa.CheckConstraint("position >= 1", name=op.f("ck_portfolio_entries_position_positive")),
        sa.CheckConstraint(
            "year BETWEEN 1900 AND 2100", name=op.f("ck_portfolio_entries_year_range")
        ),
        sa.ForeignKeyConstraint(
            ["project_type"], ["project_types.key"], name="fk_portfolio_entries_project_type"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.id"],
            name="fk_portfolio_entries_project",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_portfolio_entries_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portfolio_entries")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_portfolio_entries_tenant_id_id"),
    )
    op.create_index(
        op.f("ix_portfolio_entries_project_id"), "portfolio_entries", ["project_id"], unique=False
    )
    op.create_index(
        op.f("ix_portfolio_entries_tenant_id"), "portfolio_entries", ["tenant_id"], unique=False
    )
    op.create_table(
        "portfolio_photos",
        sa.Column("entry_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("file_id", sa.Text(), nullable=False),
        sa.Column("image_type", sa.Text(), nullable=False),
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
        sa.CheckConstraint(
            "image_type IN ('image/png', 'image/jpeg', 'image/webp')",
            name=op.f("ck_portfolio_photos_image_type_known"),
        ),
        sa.CheckConstraint("position >= 1", name=op.f("ck_portfolio_photos_position_positive")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "entry_id"],
            ["portfolio_entries.tenant_id", "portfolio_entries.id"],
            name="fk_portfolio_photos_entry",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_portfolio_photos_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portfolio_photos")),
    )
    op.create_index(
        op.f("ix_portfolio_photos_entry_id"), "portfolio_photos", ["entry_id"], unique=False
    )
    op.create_index(
        op.f("ix_portfolio_photos_tenant_id"), "portfolio_photos", ["tenant_id"], unique=False
    )
    op.create_table(
        "portfolio_videos",
        sa.Column("entry_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("file_id", sa.Text(), nullable=False),
        sa.Column("video_type", sa.Text(), nullable=False),
        sa.Column("poster_file_id", sa.Text(), nullable=False),
        sa.Column("poster_type", sa.Text(), nullable=False),
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
        sa.CheckConstraint(
            "poster_type IN ('image/png', 'image/jpeg', 'image/webp')",
            name=op.f("ck_portfolio_videos_poster_type_known"),
        ),
        sa.CheckConstraint(
            "video_type IN ('video/mp4', 'video/webm')",
            name=op.f("ck_portfolio_videos_video_type_known"),
        ),
        sa.CheckConstraint("position >= 1", name=op.f("ck_portfolio_videos_position_positive")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "entry_id"],
            ["portfolio_entries.tenant_id", "portfolio_entries.id"],
            name="fk_portfolio_videos_entry",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_portfolio_videos_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portfolio_videos")),
    )
    op.create_index(
        op.f("ix_portfolio_videos_entry_id"), "portfolio_videos", ["entry_id"], unique=False
    )
    op.create_index(
        op.f("ix_portfolio_videos_tenant_id"), "portfolio_videos", ["tenant_id"], unique=False
    )

    for table in TABLES:
        # Tenant isolation (from backend/migrations/snippets.py, pasted as it was).
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            "USING (tenant_id = current_tenant_id()) "
            "WITH CHECK (tenant_id = current_tenant_id())"
        )
    for table in ("portfolios", "portfolio_entries"):
        op.execute(
            f"CREATE TRIGGER {table}_set_updated_at BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
        )
    op.execute(
        """
        DO $$
        DECLARE app_role text := current_database() || '_app';
                operator_role text := current_database() || '_operator';
        BEGIN
            EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON portfolios, '
                           'portfolio_entries, portfolio_photos, portfolio_videos TO %I',
                           app_role);
            EXECUTE format('GRANT SELECT, DELETE ON portfolios, portfolio_entries, '
                           'portfolio_photos, portfolio_videos TO %I', operator_role);
        END $$
        """
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_portfolio_videos_tenant_id"), table_name="portfolio_videos")
    op.drop_index(op.f("ix_portfolio_videos_entry_id"), table_name="portfolio_videos")
    op.drop_table("portfolio_videos")
    op.drop_index(op.f("ix_portfolio_photos_tenant_id"), table_name="portfolio_photos")
    op.drop_index(op.f("ix_portfolio_photos_entry_id"), table_name="portfolio_photos")
    op.drop_table("portfolio_photos")
    op.drop_index(op.f("ix_portfolio_entries_tenant_id"), table_name="portfolio_entries")
    op.drop_index(op.f("ix_portfolio_entries_project_id"), table_name="portfolio_entries")
    op.drop_table("portfolio_entries")
    op.drop_index(op.f("ix_portfolios_tenant_id"), table_name="portfolios")
    op.drop_table("portfolios")
