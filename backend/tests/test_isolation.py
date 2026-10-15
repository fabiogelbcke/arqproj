"""Tenants cannot see or change each other's rows, even if code forgets a filter.

Runs against its own throwaway database with committed data, because it needs two
different logins: the owner sets things up, the app's restricted role is tested.
`tenant_rows` stands in for the first real tenant table (projects, step 2.1),
set up exactly the way its migration will be.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID

import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.orm import Session
from sqlalchemy.pool import QueuePool

from backend.commands import local_db
from backend.commands.provision import provision_url
from backend.db.isolation import TENANT_SETTING, scope_to_tenant
from backend.migrations.snippets import enable_tenant_isolation_sql, grant_to_app_sql
from backend.tests.conftest import RUNTIME_ROLE, TEST_DATABASE_URL, alembic_config

DATABASE = "arqproj_test_isolation"


@dataclass
class Tenants:
    alinea: UUID
    norte: UUID
    app: Engine  # connects as the app's restricted role


@pytest.fixture
def tenants() -> Iterator[Tenants]:
    owner_url = make_url(TEST_DATABASE_URL).set(database=DATABASE)
    runtime_url = owner_url.set(username=RUNTIME_ROLE)
    local_db.create_runtime_role(RUNTIME_ROLE)
    local_db.drop_database(DATABASE)
    local_db.create_database(DATABASE)
    owner_dsn = owner_url.render_as_string(hide_password=False)
    local_db.require_local_server(owner_dsn)  # before anything is written
    command.upgrade(alembic_config(owner_dsn), "head")
    provision_url(owner_dsn, RUNTIME_ROLE)

    owner = create_engine(owner_url)
    with owner.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE tenant_rows (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), "
                "tenant_id uuid NOT NULL REFERENCES tenants(id), name text NOT NULL)"
            )
        )
        for statement in enable_tenant_isolation_sql("tenant_rows"):
            conn.execute(text(statement))
        conn.execute(text(grant_to_app_sql("SELECT, INSERT, UPDATE, DELETE", "tenant_rows")))
        ids = {}
        for slug in ("alinea", "norte"):
            ids[slug] = conn.scalar(
                text("INSERT INTO tenants (slug, name) VALUES (:s, :s) RETURNING id"), {"s": slug}
            )
            # Same project name in both tenants on purpose.
            conn.execute(
                text("INSERT INTO tenant_rows (tenant_id, name) VALUES (:t, 'Casa Jardim')"),
                {"t": ids[slug]},
            )
    owner.dispose()

    app = create_engine(runtime_url, poolclass=QueuePool, pool_size=1, max_overflow=0)
    yield Tenants(alinea=ids["alinea"], norte=ids["norte"], app=app)
    app.dispose()
    local_db.drop_database(DATABASE)


def set_tenant(conn, tenant_id) -> None:
    conn.execute(
        text("SELECT set_config(:k, :v, true)"), {"k": TENANT_SETTING, "v": str(tenant_id)}
    )


def visible(conn) -> list[UUID]:
    # Deliberately no WHERE clause: the database must do the filtering.
    return list(conn.scalars(text("SELECT tenant_id FROM tenant_rows")))


# -- the role the app connects as ---------------------------------------------


def test_the_app_role_cannot_bypass_isolation(tenants):
    with tenants.app.connect() as conn:
        role = conn.execute(
            text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
        ).one()
        owner = conn.scalar(
            text("SELECT tableowner FROM pg_tables WHERE tablename = 'tenant_rows'")
        )
    assert tuple(role) == (False, False)
    assert owner != RUNTIME_ROLE


def test_the_app_role_cannot_switch_isolation_off(tenants):
    with tenants.app.connect() as conn:
        conn.execute(text("SET row_security = off"))
        with pytest.raises(DBAPIError, match="row-level security"):
            visible(conn)


def test_the_app_role_cannot_change_tenants_or_the_schema(tenants):
    with tenants.app.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM tenants")) == 2  # registry is readable
        with pytest.raises(ProgrammingError, match="permission denied"):
            conn.execute(text("UPDATE tenants SET name = 'x'"))
    with tenants.app.connect() as conn, pytest.raises(ProgrammingError, match="permission denied"):
        conn.execute(text("CREATE TABLE sneaky (id int)"))


# -- reading and writing -------------------------------------------------------


def test_each_tenant_sees_only_its_rows(tenants):
    with tenants.app.begin() as conn:
        set_tenant(conn, tenants.alinea)
        assert visible(conn) == [tenants.alinea]
    with tenants.app.begin() as conn:
        set_tenant(conn, tenants.norte)
        assert visible(conn) == [tenants.norte]


def test_no_tenant_means_no_rows(tenants):
    with tenants.app.connect() as conn:
        assert visible(conn) == []


def test_writing_another_tenants_row_is_refused(tenants):
    with tenants.app.connect() as conn, conn.begin():
        set_tenant(conn, tenants.alinea)
        with pytest.raises(ProgrammingError, match="row-level security"):
            conn.execute(
                text("INSERT INTO tenant_rows (tenant_id, name) VALUES (:t, 'x')"),
                {"t": tenants.norte},
            )


def test_inserts_get_the_current_tenant_without_naming_it(tenants):
    with tenants.app.begin() as conn:
        set_tenant(conn, tenants.norte)
        conn.execute(text("INSERT INTO tenant_rows (name) VALUES ('Casa Lago')"))
        owner = conn.scalar(text("SELECT tenant_id FROM tenant_rows WHERE name = 'Casa Lago'"))
    assert owner == tenants.norte


def test_an_insert_with_no_tenant_set_fails(tenants):
    # The default is NULL then; the policy refuses the row (before NOT NULL would).
    with tenants.app.connect() as conn, pytest.raises(DBAPIError, match="row-level security"):
        conn.execute(text("INSERT INTO tenant_rows (name) VALUES ('Sem escritório')"))


def test_moving_a_row_to_another_tenant_is_refused(tenants):
    with tenants.app.connect() as conn, conn.begin():
        set_tenant(conn, tenants.alinea)
        with pytest.raises(ProgrammingError, match="row-level security"):
            conn.execute(text("UPDATE tenant_rows SET tenant_id = :t"), {"t": tenants.norte})


def test_another_tenants_rows_cannot_be_changed_or_deleted(tenants):
    with tenants.app.begin() as conn:
        set_tenant(conn, tenants.alinea)
        # Matching zero rows, silently: the other tenant's row is invisible here.
        assert (
            conn.execute(
                text("DELETE FROM tenant_rows WHERE tenant_id = :t"), {"t": tenants.norte}
            ).rowcount
            == 0
        )
    with tenants.app.begin() as conn:
        set_tenant(conn, tenants.norte)
        assert visible(conn) == [tenants.norte]


# -- the tenant never leaks between requests -------------------------------------


def test_a_reused_connection_forgets_the_previous_tenant(tenants):
    # Pool of exactly one connection: the second checkout is the same connection.
    with tenants.app.begin() as conn:
        set_tenant(conn, tenants.alinea)
        first = conn.connection.dbapi_connection
        assert visible(conn) == [tenants.alinea]
    with tenants.app.connect() as conn:
        assert conn.connection.dbapi_connection is first
        assert visible(conn) == []


def test_an_tenant_session_is_scoped_in_every_transaction(tenants):
    with Session(tenants.app) as session:
        scope_to_tenant(session, tenants.alinea)
        assert visible(session) == [tenants.alinea]
        session.commit()  # the next query starts a new transaction...
        assert visible(session) == [tenants.alinea]  # ...which is scoped again
        session.rollback()
        assert visible(session) == [tenants.alinea]


def test_an_unscoped_session_sees_nothing(tenants):
    with Session(tenants.app) as session:
        assert visible(session) == []
