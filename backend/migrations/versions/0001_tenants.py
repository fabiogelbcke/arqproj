"""Offices (tenants) and their addresses; the updated_at trigger.

Revision: 0001
Previous: none
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Shared by every table with updated_at: keeps it current even for changes
    # made outside the ORM (manual fixes, scripts). clock_timestamp() is the moment
    # of the change; now() would be the start of the transaction.
    op.execute(
        """
        CREATE FUNCTION set_updated_at() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            NEW.updated_at = clock_timestamp();
            RETURN NEW;
        END;
        $$
        """
    )

    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("locale", sa.Text(), server_default=sa.text("'pt-BR'"), nullable=False),
        sa.Column(
            "timezone", sa.Text(), server_default=sa.text("'America/Sao_Paulo'"), nullable=False
        ),
        sa.Column("status", sa.Text(), server_default=sa.text("'active'"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            r"slug ~ '^[a-z0-9]([a-z0-9-]*[a-z0-9])?$'", name=op.f("ck_tenants_slug_format")
        ),
        sa.CheckConstraint("length(btrim(name)) > 0", name=op.f("ck_tenants_name_not_blank")),
        sa.CheckConstraint(
            "status IN ('active', 'suspended')", name=op.f("ck_tenants_status_known")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenants")),
        sa.UniqueConstraint("slug", name=op.f("uq_tenants_slug")),
    )
    op.execute(
        "CREATE TRIGGER tenants_set_updated_at BEFORE UPDATE ON tenants "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )

    op.create_table(
        "tenant_domains",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("hostname", sa.Text(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            r"hostname ~ '^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$'",
            name=op.f("ck_tenant_domains_hostname_format"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_tenant_domains_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenant_domains")),
        sa.UniqueConstraint("hostname", name=op.f("uq_tenant_domains_hostname")),
    )
    op.create_index("ix_tenant_domains_tenant_id", "tenant_domains", ["tenant_id"])
    op.create_index(
        "uq_tenant_domains_one_primary",
        "tenant_domains",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("is_primary"),
    )


def downgrade() -> None:
    op.drop_table("tenant_domains")
    op.drop_table("tenants")
    op.execute("DROP FUNCTION set_updated_at()")
