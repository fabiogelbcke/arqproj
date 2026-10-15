"""Office isolation: current_tenant_id() and the app's read-only registry access.

Revision: 0002
Previous: 0001

Tables holding office data (projects onwards) enable row-level security with
backend.db.isolation.enable_office_isolation_sql in their own migrations. The
app's runtime role gets only the privileges each migration grants it.
"""

from collections.abc import Sequence

from alembic import context, op

from backend.db.isolation import OFFICE_SETTING, grant_sql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _runtime_role() -> str:
    return context.config.attributes["runtime_role"]


def upgrade() -> None:
    # The office set on the current transaction, or NULL. NULL matches no row, so
    # a query without an office sees nothing instead of failing on ''::uuid.
    op.execute(
        f"""
        CREATE FUNCTION current_tenant_id() RETURNS uuid
        LANGUAGE sql STABLE AS $$
            SELECT NULLIF(current_setting('{OFFICE_SETTING}', true), '')::uuid
        $$
        """
    )
    role = _runtime_role()
    op.execute(f'GRANT USAGE ON SCHEMA public TO "{role}"')
    # The routing registry: read to resolve a request's hostname, never written by
    # the app (offices and addresses are managed by owner-run commands for now).
    op.execute(grant_sql("SELECT", "tenants", role))
    op.execute(grant_sql("SELECT", "tenant_domains", role))


def downgrade() -> None:
    role = _runtime_role()
    op.execute(f'REVOKE SELECT ON tenant_domains FROM "{role}"')
    op.execute(f'REVOKE SELECT ON tenants FROM "{role}"')
    op.execute(f'REVOKE USAGE ON SCHEMA public FROM "{role}"')
    op.execute("DROP FUNCTION current_tenant_id()")
