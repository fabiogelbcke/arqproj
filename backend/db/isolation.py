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
"""

from __future__ import annotations

import uuid

from sqlalchemy import event
from sqlalchemy.orm import Session

OFFICE_SETTING = "app.tenant_id"
POLICY = "office_isolation"
# Tables with a tenant_id that are deliberately not under the policy; see above.
REGISTRY_TABLES = frozenset({"tenant_domains"})


def enable_office_isolation_sql(table: str) -> list[str]:
    """Statements a migration runs for every new table that holds office data."""
    return [
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
        f"CREATE POLICY {POLICY} ON {table} "
        f"USING (tenant_id = current_tenant_id()) "
        f"WITH CHECK (tenant_id = current_tenant_id())",
    ]


def grant_sql(privileges: str, table: str, role: str) -> str:
    """GRANT to the app's runtime role (quoted: Cloud SQL IAM users contain '@')."""
    return f'GRANT {privileges} ON {table} TO "{role}"'


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
