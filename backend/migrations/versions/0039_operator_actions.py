"""Audited operator actions with a separate, limited database role (A38).

Approved 26 Oct 2026. Does not grant the app role any new privileges.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0039"
down_revision: str | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "operator_audit_events",
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target_tenant_id", sa.Uuid(), nullable=False),
        sa.Column("target_slug", sa.Text(), nullable=False),
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_operator_audit_events")),
    )
    op.create_index(
        op.f("ix_operator_audit_events_target_tenant_id"),
        "operator_audit_events",
        ["target_tenant_id"],
    )
    op.execute("""
        DO $$
        DECLARE operator_role text := current_database() || '_operator';
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = operator_role) THEN
                EXECUTE format('CREATE ROLE %I NOLOGIN', operator_role);
            END IF;
            EXECUTE format('GRANT USAGE ON SCHEMA public TO %I', operator_role);
            EXECUTE format('GRANT SELECT, INSERT, DELETE ON tenants, tenant_domains TO %I',
                           operator_role);
            EXECUTE format('GRANT UPDATE (status) ON tenants TO %I', operator_role);
            EXECUTE format('GRANT SELECT, INSERT ON join_links TO %I', operator_role);
            EXECUTE format('GRANT SELECT, INSERT ON operator_audit_events TO %I', operator_role);
            EXECUTE format('GRANT SELECT, DELETE ON share_link_files, project_events, '
                'notification_deliveries, share_links, sessions, project_stages, project_slugs, '
                'project_recipients, project_files_seen, project_details, password_links, '
                'notification_batches, meetings, join_links, users, storage_connections, '
                'projects, office_profiles TO %I', operator_role);
        END $$
    """)


def downgrade() -> None:
    op.drop_table("operator_audit_events")
    op.execute("""
        DO $$
        DECLARE operator_role text := current_database() || '_operator';
        BEGIN
            EXECUTE format('REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM %I',
                           operator_role);
            EXECUTE format('REVOKE USAGE ON SCHEMA public FROM %I', operator_role);
            -- Keep the empty NOLOGIN role: provisioned logins may still be members.
            -- A rollback revokes its capabilities without managing external identities.
        END $$
    """)
