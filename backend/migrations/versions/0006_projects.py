"""Projects, their slugs, stages, details and meetings; all tenant-isolated.

Revision: 0006
Previous: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("client_name", sa.Text(), nullable=False),
        sa.Column("project_type", sa.Text(), nullable=False),
        sa.Column("stage_template", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'draft'"), nullable=False),
        sa.Column("access_mode", sa.Text(), server_default=sa.text("'public'"), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("access_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("current_position", sa.Integer(), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("row_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
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
            "access_mode <> 'password' OR password_hash IS NOT NULL",
            name=op.f("ck_projects_password_set"),
        ),
        sa.CheckConstraint(
            "access_mode IN ('public', 'password')", name=op.f("ck_projects_access_mode_known")
        ),
        sa.CheckConstraint(
            "project_type IN ('architecture', 'interiors', 'renovation', 'landscaping')",
            name=op.f("ck_projects_project_type_known"),
        ),
        sa.CheckConstraint(
            "stage_template IN ('standard', 'interiors', 'empty')",
            name=op.f("ck_projects_stage_template_known"),
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'completed', 'archived')",
            name=op.f("ck_projects_status_known"),
        ),
        sa.CheckConstraint(
            "current_position IS NULL OR current_position >= 1",
            name=op.f("ck_projects_position_positive"),
        ),
        sa.CheckConstraint(
            "length(btrim(client_name)) BETWEEN 1 AND 48",
            name=op.f("ck_projects_client_name_length"),
        ),
        sa.CheckConstraint("length(btrim(name)) > 0", name=op.f("ck_projects_name_not_blank")),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_projects_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_projects_tenant_id_id"),
    )
    op.create_index(op.f("ix_projects_tenant_id"), "projects", ["tenant_id"], unique=False)
    op.create_table(
        "meetings",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("link", sa.Text(), nullable=True),
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
            "link IS NULL OR link ~ '^https?://\\S+$'", name=op.f("ck_meetings_link_is_web")
        ),
        sa.CheckConstraint("ends_at > starts_at", name=op.f("ck_meetings_ends_after_start")),
        sa.CheckConstraint(
            "length(btrim(title)) BETWEEN 1 AND 40", name=op.f("ck_meetings_title_length")
        ),
        sa.CheckConstraint(
            "location IS NULL OR length(location) <= 60", name=op.f("ck_meetings_location_length")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.id"],
            name="fk_meetings_project",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_meetings_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_meetings")),
    )
    op.create_index(
        "ix_meetings_project_id_starts_at", "meetings", ["project_id", "starts_at"], unique=False
    )
    op.create_index(op.f("ix_meetings_tenant_id"), "meetings", ["tenant_id"], unique=False)
    op.create_table(
        "project_details",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("value_number", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("value_date", sa.Date(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "tenant_id", sa.Uuid(), server_default=sa.text("current_tenant_id()"), nullable=False
        ),
        sa.CheckConstraint(
            (
                "(key IN ('client', 'location', 'responsible') "
                "AND value_text IS NOT NULL AND value_number IS NULL AND value_date IS NULL) OR "
                "(key IN ('site_area', 'built_area') "
                "AND value_text IS NULL AND value_number IS NOT NULL AND value_date IS NULL) OR "
                "(key IN ('start_date', 'expected_delivery') "
                "AND value_text IS NULL AND value_number IS NULL AND value_date IS NOT NULL)"
            ),
            name=op.f("ck_project_details_value_matches_type"),
        ),
        sa.CheckConstraint(
            (
                "key IN ('client', 'location', 'site_area', 'built_area', 'start_date', "
                "'expected_delivery', 'responsible')"
            ),
            name=op.f("ck_project_details_key_known"),
        ),
        sa.CheckConstraint(
            "value_number IS NULL OR value_number >= 0",
            name=op.f("ck_project_details_number_not_negative"),
        ),
        sa.CheckConstraint(
            "value_text IS NULL OR length(btrim(value_text)) > 0",
            name=op.f("ck_project_details_text_not_blank"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.id"],
            name="fk_project_details_project",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_project_details_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_details")),
        sa.UniqueConstraint("project_id", "key", name="uq_project_details_project_id_key"),
        sa.UniqueConstraint(
            "project_id",
            "position",
            deferrable=True,
            initially="DEFERRED",
            name="uq_project_details_project_id_position",
        ),
    )
    op.create_index(
        op.f("ix_project_details_project_id"), "project_details", ["project_id"], unique=False
    )
    op.create_index(
        op.f("ix_project_details_tenant_id"), "project_details", ["tenant_id"], unique=False
    )
    op.create_table(
        "project_slugs",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("is_current", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "tenant_id", sa.Uuid(), server_default=sa.text("current_tenant_id()"), nullable=False
        ),
        sa.CheckConstraint(
            "slug NOT IN ('painel', 'api', 'static', 'assets', 'health')",
            name=op.f("ck_project_slugs_slug_not_reserved"),
        ),
        sa.CheckConstraint(
            "slug ~ '^[a-z0-9]([a-z0-9-]*[a-z0-9])?$'", name=op.f("ck_project_slugs_slug_format")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.id"],
            name="fk_project_slugs_project",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_project_slugs_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_slugs")),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_project_slugs_tenant_id_slug"),
    )
    op.create_index(
        op.f("ix_project_slugs_project_id"), "project_slugs", ["project_id"], unique=False
    )
    op.create_index(
        op.f("ix_project_slugs_tenant_id"), "project_slugs", ["tenant_id"], unique=False
    )
    op.create_index(
        "uq_project_slugs_one_current",
        "project_slugs",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )
    op.create_table(
        "project_stages",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("builtin_key", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("about", sa.Text(), nullable=True),
        sa.Column("deliverables", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("notes_updated_at", sa.DateTime(timezone=True), nullable=True),
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
            (
                "builtin_key IN ('proposal', 'briefing_survey', 'preliminary_studies', 'model_3d', "
                "'construction_documents', 'final_delivery', 'extra_services', 'briefing', "
                "'layout', 'detailing')"
            ),
            name=op.f("ck_project_stages_builtin_key_known"),
        ),
        sa.CheckConstraint(
            "(builtin_key IS NULL) = (title IS NOT NULL)",
            name=op.f("ck_project_stages_builtin_or_custom"),
        ),
        sa.CheckConstraint(
            "builtin_key IS NULL OR (about IS NULL AND deliverables IS NULL)",
            name=op.f("ck_project_stages_builtin_texts_translated"),
        ),
        sa.CheckConstraint("position >= 1", name=op.f("ck_project_stages_position_positive")),
        sa.CheckConstraint(
            "title IS NULL OR length(btrim(title)) > 0",
            name=op.f("ck_project_stages_title_not_blank"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.id"],
            name="fk_project_stages_project",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_project_stages_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_stages")),
        sa.UniqueConstraint(
            "project_id",
            "position",
            deferrable=True,
            initially="DEFERRED",
            name="uq_project_stages_project_id_position",
        ),
    )
    op.create_index(
        op.f("ix_project_stages_project_id"), "project_stages", ["project_id"], unique=False
    )
    op.create_index(
        op.f("ix_project_stages_tenant_id"), "project_stages", ["tenant_id"], unique=False
    )

    tables = ("projects", "project_slugs", "project_stages", "project_details", "meetings")
    for table in ("projects", "project_stages", "meetings"):
        op.execute(
            f"CREATE TRIGGER {table}_set_updated_at BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
        )

    # Tenant isolation (from backend/migrations/snippets.py, pasted as it was).
    for table in tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            "USING (tenant_id = current_tenant_id()) "
            "WITH CHECK (tenant_id = current_tenant_id())"
        )

    # The app only reads projects for now; editing arrives with slice 3.
    op.execute(
        """
        DO $$
        DECLARE app_role text := current_database() || '_app';
        BEGIN
            EXECUTE format(
                'GRANT SELECT ON projects, project_slugs, project_stages, project_details, '
                'meetings TO %I',
                app_role
            );
        END $$
        """
    )


def downgrade() -> None:
    for table in ("meetings", "project_details", "project_stages", "project_slugs", "projects"):
        op.drop_table(table)
