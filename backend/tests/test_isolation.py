"""Offices cannot see or change each other's rows, even if code forgets a filter.

Runs against its own throwaway database with committed data, because it needs two
different logins: the owner sets things up, the app's restricted role is tested.
`office_rows` stands in for the first real office table (projects, step 2.1),
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

from backend.db import local
from backend.db.isolation import OFFICE_SETTING, scope_to_office
from backend.db.provision import provision_url
from backend.migrations.snippets import enable_office_isolation_sql, grant_to_app_sql
from backend.tests.conftest import RUNTIME_ROLE, TEST_DATABASE_URL, alembic_config

DATABASE = "arqproj_test_isolation"


@dataclass
class Offices:
    alinea: UUID
    norte: UUID
    app: Engine  # connects as the app's restricted role


@pytest.fixture
def offices() -> Iterator[Offices]:
    owner_url = make_url(TEST_DATABASE_URL).set(database=DATABASE)
    runtime_url = owner_url.set(username=RUNTIME_ROLE)
    local.require_local(owner_url.render_as_string(hide_password=False))
    local.create_runtime_role(RUNTIME_ROLE)
    local.drop_database(DATABASE)
    local.create_database(DATABASE)
    owner_dsn = owner_url.render_as_string(hide_password=False)
    command.upgrade(alembic_config(owner_dsn), "head")
    provision_url(owner_dsn, RUNTIME_ROLE)

    owner = create_engine(owner_url)
    with owner.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE office_rows (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), "
                "tenant_id uuid NOT NULL REFERENCES tenants(id), name text NOT NULL)"
            )
        )
        for statement in enable_office_isolation_sql("office_rows"):
            conn.execute(text(statement))
        conn.execute(text(grant_to_app_sql("SELECT, INSERT, UPDATE, DELETE", "office_rows")))
        ids = {}
        for slug in ("alinea", "norte"):
            ids[slug] = conn.scalar(
                text("INSERT INTO tenants (slug, name) VALUES (:s, :s) RETURNING id"), {"s": slug}
            )
            # Same project name in both offices on purpose.
            conn.execute(
                text("INSERT INTO office_rows (tenant_id, name) VALUES (:t, 'Casa Jardim')"),
                {"t": ids[slug]},
            )
    owner.dispose()

    app = create_engine(runtime_url, poolclass=QueuePool, pool_size=1, max_overflow=0)
    yield Offices(alinea=ids["alinea"], norte=ids["norte"], app=app)
    app.dispose()
    local.drop_database(DATABASE)


def set_office(conn, office_id) -> None:
    conn.execute(
        text("SELECT set_config(:k, :v, true)"), {"k": OFFICE_SETTING, "v": str(office_id)}
    )


def visible(conn) -> list[UUID]:
    # Deliberately no WHERE clause: the database must do the filtering.
    return list(conn.scalars(text("SELECT tenant_id FROM office_rows")))


# -- the role the app connects as ---------------------------------------------


def test_the_app_role_cannot_bypass_isolation(offices):
    with offices.app.connect() as conn:
        role = conn.execute(
            text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
        ).one()
        owner = conn.scalar(
            text("SELECT tableowner FROM pg_tables WHERE tablename = 'office_rows'")
        )
    assert tuple(role) == (False, False)
    assert owner != RUNTIME_ROLE


def test_the_app_role_cannot_switch_isolation_off(offices):
    with offices.app.connect() as conn:
        conn.execute(text("SET row_security = off"))
        with pytest.raises(DBAPIError, match="row-level security"):
            visible(conn)


def test_the_app_role_cannot_change_offices_or_the_schema(offices):
    with offices.app.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM tenants")) == 2  # registry is readable
        with pytest.raises(ProgrammingError, match="permission denied"):
            conn.execute(text("UPDATE tenants SET name = 'x'"))
    with offices.app.connect() as conn, pytest.raises(ProgrammingError, match="permission denied"):
        conn.execute(text("CREATE TABLE sneaky (id int)"))


# -- reading and writing -------------------------------------------------------


def test_each_office_sees_only_its_rows(offices):
    with offices.app.begin() as conn:
        set_office(conn, offices.alinea)
        assert visible(conn) == [offices.alinea]
    with offices.app.begin() as conn:
        set_office(conn, offices.norte)
        assert visible(conn) == [offices.norte]


def test_no_office_means_no_rows(offices):
    with offices.app.connect() as conn:
        assert visible(conn) == []


def test_writing_another_offices_row_is_refused(offices):
    with offices.app.connect() as conn, conn.begin():
        set_office(conn, offices.alinea)
        with pytest.raises(ProgrammingError, match="row-level security"):
            conn.execute(
                text("INSERT INTO office_rows (tenant_id, name) VALUES (:t, 'x')"),
                {"t": offices.norte},
            )


def test_inserts_get_the_current_office_without_naming_it(offices):
    with offices.app.begin() as conn:
        set_office(conn, offices.norte)
        conn.execute(text("INSERT INTO office_rows (name) VALUES ('Casa Lago')"))
        owner = conn.scalar(text("SELECT tenant_id FROM office_rows WHERE name = 'Casa Lago'"))
    assert owner == offices.norte


def test_an_insert_with_no_office_set_fails(offices):
    # The default is NULL then; the policy refuses the row (before NOT NULL would).
    with offices.app.connect() as conn, pytest.raises(DBAPIError, match="row-level security"):
        conn.execute(text("INSERT INTO office_rows (name) VALUES ('Sem escritório')"))


def test_moving_a_row_to_another_office_is_refused(offices):
    with offices.app.connect() as conn, conn.begin():
        set_office(conn, offices.alinea)
        with pytest.raises(ProgrammingError, match="row-level security"):
            conn.execute(text("UPDATE office_rows SET tenant_id = :t"), {"t": offices.norte})


def test_another_offices_rows_cannot_be_changed_or_deleted(offices):
    with offices.app.begin() as conn:
        set_office(conn, offices.alinea)
        # Matching zero rows, silently: the other office's row is invisible here.
        assert (
            conn.execute(
                text("DELETE FROM office_rows WHERE tenant_id = :t"), {"t": offices.norte}
            ).rowcount
            == 0
        )
    with offices.app.begin() as conn:
        set_office(conn, offices.norte)
        assert visible(conn) == [offices.norte]


# -- the office never leaks between requests -------------------------------------


def test_a_reused_connection_forgets_the_previous_office(offices):
    # Pool of exactly one connection: the second checkout is the same connection.
    with offices.app.begin() as conn:
        set_office(conn, offices.alinea)
        first = conn.connection.dbapi_connection
        assert visible(conn) == [offices.alinea]
    with offices.app.connect() as conn:
        assert conn.connection.dbapi_connection is first
        assert visible(conn) == []


def test_an_office_session_is_scoped_in_every_transaction(offices):
    with Session(offices.app) as session:
        scope_to_office(session, offices.alinea)
        assert visible(session) == [offices.alinea]
        session.commit()  # the next query starts a new transaction...
        assert visible(session) == [offices.alinea]  # ...which is scoped again
        session.rollback()
        assert visible(session) == [offices.alinea]


def test_an_unscoped_session_sees_nothing(offices):
    with Session(offices.app) as session:
        assert visible(session) == []
