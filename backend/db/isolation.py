"""Telling PostgreSQL which tenant each transaction is for. Runs on every request.

Isolation itself is enforced inside PostgreSQL by row-level security, set up once
per table by its migration (see `backend/migrations/snippets.py`): a row is
visible or writable only when its `tenant_id` equals the tenant set on the
current transaction. The app's only job is to set that tenant, which this module
does:

- `scope_to_tenant` marks a session as belonging to a tenant.
- `_apply_tenant` sets it at the start of every transaction that session begins,
  with `set_config(..., true)`, which reverts when the transaction ends. So a
  pooled connection never carries one request's tenant into the next, and a
  session with no tenant sees no tenant rows at all.
- `TenantOwned` gives models a `tenant_id` that PostgreSQL fills in with the
  current tenant, so code never sets it.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, event, text
from sqlalchemy.orm import Mapped, Session, mapped_column

TENANT_SETTING = "app.tenant_id"


class TenantOwned:
    """Model mixin for tables holding tenant data.

    `tenant_id` defaults to the current transaction's tenant, so code never sets
    it. The table's migration must also enable isolation (a schema test fails
    otherwise); see `backend/migrations/snippets.py`.
    """

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id"), index=True, server_default=text("current_tenant_id()")
    )


def scope_to_tenant(session: Session, tenant_id: uuid.UUID) -> None:
    """Every transaction this session begins from now on is for this tenant."""
    session.info["tenant_id"] = tenant_id


@event.listens_for(Session, "after_begin")
def _apply_tenant(session: Session, transaction, connection) -> None:
    tenant_id = session.info.get("tenant_id")
    if tenant_id is not None:
        connection.exec_driver_sql(
            "SELECT set_config(%s, %s, true)", (TENANT_SETTING, str(tenant_id))
        )
