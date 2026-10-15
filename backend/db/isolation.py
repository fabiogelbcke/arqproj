"""Keeping each office's rows away from every other office, enforced by PostgreSQL.

Two layers (decision D6):

1. **Row-level security.** Every table holding office data has a `tenant_id` and
   the `office_isolation` policy: a row is visible or writable only when its
   `tenant_id` equals the office set on the current transaction. With no office
   set, a query sees nothing and writes are refused. The app connects as a
   restricted role that cannot bypass this (not superuser, no BYPASSRLS, not the
   tables' owner), and the policy is FORCEd so even the owner is bound unless it
   is a superuser.
2. **The office is set per transaction**, never per connection: `set_config(...,
   true)` reverts when the transaction ends, so a pooled connection never carries
   one request's office into the next. A session opened for an office sets it at
   the start of every transaction it begins (see `_apply_office`).

`tenants` and `tenant_domains` are the routing registry, read before any office
is known (to resolve the request's hostname), so they are protected by grants
(read-only for the app) rather than by this policy.

Privileges go to a per-database group role (`<database>_app`), never to a login;
`backend.db.provision` makes the configured login a member of it.

**Migrations paste SQL, they do not import it.** The helpers below generate the
statements a new office-data table needs; copy their output into the migration
so it replays exactly as it first ran, even if these helpers change later.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, event, text
from sqlalchemy.orm import Mapped, Session, mapped_column

OFFICE_SETTING = "app.tenant_id"
POLICY = "office_isolation"
# Tables with a tenant_id that are deliberately not under the policy; see above.
REGISTRY_TABLES = frozenset({"tenant_domains"})


# The current definition of current_tenant_id(), as the latest migration left it.
# Used to build the models-only database in schema tests; a test compares it with
# the migrated database, so a change made in only one place fails.
CURRENT_TENANT_FUNCTION_SQL = f"""
CREATE FUNCTION current_tenant_id() RETURNS uuid
LANGUAGE sql STABLE AS $$
    SELECT NULLIF(current_setting('{OFFICE_SETTING}', true), '')::uuid
$$
"""


def enable_office_isolation_sql(table: str) -> list[str]:
    """Statements a migration runs for every new table that holds office data.

    The default fills `tenant_id` with the current office when an insert leaves it
    out; the policy is what enforces it: a different office is refused, and with
    no office set the default is NULL, which the policy refuses too.
    """
    return [
        f"ALTER TABLE {table} ALTER COLUMN tenant_id SET DEFAULT current_tenant_id()",
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
        f"CREATE POLICY {POLICY} ON {table} "
        f"USING (tenant_id = current_tenant_id()) "
        f"WITH CHECK (tenant_id = current_tenant_id())",
    ]


class OfficeOwned:
    """Model mixin for tables holding office data.

    `tenant_id` defaults to the current transaction's office, so code never sets it.
    The table's migration must also run `enable_office_isolation_sql` (a schema
    test fails otherwise).
    """

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id"), index=True, server_default=text("current_tenant_id()")
    )


def app_role_for(database: str) -> str:
    """The group role holding the app's privileges in this database."""
    return f"{database}_app"


def grant_to_app_sql(privileges: str, table: str) -> str:
    """GRANT to this database's app group role, resolved inside PostgreSQL."""
    return (
        "DO $$ BEGIN EXECUTE format("
        f"'GRANT {privileges} ON {table} TO %I', current_database() || '_app'"
        "); END $$"
    )


def scope_to_office(session: Session, office_id: uuid.UUID) -> None:
    """Every transaction this session begins from now on is for this office."""
    session.info["office_id"] = office_id


@event.listens_for(Session, "after_begin")
def _apply_office(session: Session, transaction, connection) -> None:
    office_id = session.info.get("office_id")
    if office_id is not None:
        connection.exec_driver_sql(
            "SELECT set_config(%s, %s, true)", (OFFICE_SETTING, str(office_id))
        )
