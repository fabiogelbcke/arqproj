"""Office isolation: current_tenant_id(), the app's group role, read-only registry.

Revision: 0002
Previous: 0001

Self-contained on purpose: a migration must replay exactly as it first ran, so its
SQL is written out here rather than imported from application code that may change.

Grants go to a group role named after the database (`<database>_app`, NOLOGIN),
never to a specific login. The app's login is made a member of it by
`python -m backend.db.provision`, run after migrations; rotating the login is a
re-run of that command, not a migration. Naming the role after the database keeps
staging and production apart when they share one PostgreSQL instance.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The office set on the current transaction, or NULL. NULL matches no row, so a
    # query without an office sees nothing instead of failing on ''::uuid.
    op.execute(
        """
        CREATE FUNCTION current_tenant_id() RETURNS uuid
        LANGUAGE sql STABLE AS $$
            SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid
        $$
        """
    )
    # The routing registry is read to resolve a request's hostname and never written
    # by the app (offices and addresses are managed by owner-run commands for now).
    op.execute(
        """
        DO $$
        DECLARE app_role text := current_database() || '_app';
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = app_role) THEN
                EXECUTE format('CREATE ROLE %I NOLOGIN', app_role);
            END IF;
            EXECUTE format('GRANT USAGE ON SCHEMA public TO %I', app_role);
            EXECUTE format('GRANT SELECT ON tenants, tenant_domains TO %I', app_role);
        END $$
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE app_role text := current_database() || '_app';
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = app_role) THEN
                EXECUTE format('REVOKE SELECT ON tenants, tenant_domains FROM %I', app_role);
                EXECUTE format('REVOKE USAGE ON SCHEMA public FROM %I', app_role);
                EXECUTE format('DROP ROLE %I', app_role);
            END IF;
        END $$
        """
    )
    op.execute("DROP FUNCTION current_tenant_id()")
