"""Office profiles: name, contact email and logo, isolated per office.

Revision: 0010
Previous: 0009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "office_profiles",
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("contact_email", sa.Text(), nullable=True),
        sa.Column("logo_file_id", sa.Text(), nullable=True),
        sa.Column("logo_type", sa.Text(), nullable=True),
        sa.Column("brand_folder_id", sa.Text(), nullable=True),
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
            "contact_email IS NULL OR (contact_email = lower(contact_email) "
            "AND contact_email LIKE '%_@_%.__%')",
            name=op.f("ck_office_profiles_contact_email_format"),
        ),
        sa.CheckConstraint(
            "logo_type IN ('image/png', 'image/jpeg', 'image/webp', 'image/svg+xml')",
            name=op.f("ck_office_profiles_logo_type_known"),
        ),
        sa.CheckConstraint(
            "(logo_file_id IS NULL) = (logo_type IS NULL)",
            name=op.f("ck_office_profiles_logo_complete"),
        ),
        sa.CheckConstraint(
            "length(btrim(display_name)) BETWEEN 1 AND 80",
            name=op.f("ck_office_profiles_display_name_length"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_office_profiles_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_office_profiles")),
        sa.UniqueConstraint("tenant_id", name="uq_office_profiles_tenant_id"),
    )
    op.create_index(
        op.f("ix_office_profiles_tenant_id"), "office_profiles", ["tenant_id"], unique=False
    )

    op.execute(
        "CREATE TRIGGER office_profiles_set_updated_at BEFORE UPDATE ON office_profiles "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    # Tenant isolation (from backend/migrations/snippets.py, pasted as it was).
    op.execute("ALTER TABLE office_profiles ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE office_profiles FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON office_profiles "
        "USING (tenant_id = current_tenant_id()) "
        "WITH CHECK (tenant_id = current_tenant_id())"
    )
    # Owners edit their office's details from the painel (checked by the app).
    op.execute(
        """
        DO $$
        BEGIN
            EXECUTE format(
                'GRANT SELECT, INSERT, UPDATE ON office_profiles TO %I',
                current_database() || '_app'
            );
        END $$
        """
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_office_profiles_tenant_id"), table_name="office_profiles")
    op.drop_table("office_profiles")
