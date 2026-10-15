"""SQL for writing migrations that add tenant-data tables. Never used by the app.

How a new table holding tenant data (projects onwards) gets isolated:

1. Generate its statements here, e.g. `enable_tenant_isolation_sql("projects")`
   and `grant_to_app_sql("SELECT, INSERT, UPDATE, DELETE", "projects")`.
2. **Paste the output into the migration.** Migrations never import this module:
   a migration must replay exactly as it first ran, even if this file changes.

The schema tests also use these definitions, to build a database straight from
the models and to check every `tenant_id` table is isolated.

Background:

- The `tenant_isolation` policy shows or accepts a row only when its `tenant_id`
  equals `current_tenant_id()`, the tenant set on the current transaction (see
  `backend/db/isolation.py`). It is FORCEd, so even the tables' owner is bound
  unless it is a superuser.
- `tenants` and `tenant_domains` are the routing registry, read before any tenant
  is known (to resolve the request's hostname), so they are protected by grants
  (read-only for the app) rather than by the policy.
- Privileges go to a per-database group role (`<database>_app`), never to a
  login; `backend.commands.provision` makes the configured login its only member.
"""

from __future__ import annotations

from backend.db.isolation import TENANT_SETTING

POLICY = "tenant_isolation"
# Tables with a tenant_id that are deliberately not under the policy; see above.
REGISTRY_TABLES = frozenset({"tenant_domains"})

# The current definition of current_tenant_id(), as the latest migration left it.
# A schema test compares it with the migrated database, so a change made in only
# one place (here, or in a migration) fails.
CURRENT_TENANT_FUNCTION_SQL = f"""
CREATE FUNCTION current_tenant_id() RETURNS uuid
LANGUAGE sql STABLE AS $$
    SELECT NULLIF(current_setting('{TENANT_SETTING}', true), '')::uuid
$$
"""


def enable_tenant_isolation_sql(table: str) -> list[str]:
    """Statements for every new table that holds tenant data.

    The default fills `tenant_id` with the current tenant when an insert leaves it
    out; the policy is what enforces it: a different tenant is refused, and with
    no tenant set the default is NULL, which the policy refuses too.
    """
    return [
        f"ALTER TABLE {table} ALTER COLUMN tenant_id SET DEFAULT current_tenant_id()",
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
        f"CREATE POLICY {POLICY} ON {table} "
        f"USING (tenant_id = current_tenant_id()) "
        f"WITH CHECK (tenant_id = current_tenant_id())",
    ]


def grant_to_app_sql(privileges: str, table: str) -> str:
    """GRANT to this database's app group role, resolved inside PostgreSQL."""
    return (
        "DO $$ BEGIN EXECUTE format("
        f"'GRANT {privileges} ON {table} TO %I', current_database() || '_app'"
        "); END $$"
    )
