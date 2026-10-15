"""Telling PostgreSQL which office each transaction is for. Runs on every request.

Isolation itself is enforced inside PostgreSQL by row-level security, set up once
per table by its migration (see `backend/migrations/snippets.py`): a row is
visible or writable only when its `tenant_id` equals the office set on the
current transaction. The app's only job is to set that office, which this module
does:

- `scope_to_office` marks a session as belonging to an office.
- `_apply_office` sets it at the start of every transaction that session begins,
  with `set_config(..., true)`, which reverts when the transaction ends. So a
  pooled connection never carries one request's office into the next, and a
  session with no office sees no office rows at all.
- `OfficeOwned` gives models a `tenant_id` that PostgreSQL fills in with the
  current office, so code never sets it.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, event, text
from sqlalchemy.orm import Mapped, Session, mapped_column

OFFICE_SETTING = "app.tenant_id"


class OfficeOwned:
    """Model mixin for tables holding office data.

    `tenant_id` defaults to the current transaction's office, so code never sets
    it. The table's migration must also enable isolation (a schema test fails
    otherwise); see `backend/migrations/snippets.py`.
    """

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id"), index=True, server_default=text("current_tenant_id()")
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
