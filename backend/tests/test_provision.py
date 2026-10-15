"""Provisioning: the app's login gets access through the database's group role,
and only a login that is bound by tenant isolation is accepted."""

import getpass

import psycopg
import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError

from backend.commands import local_db
from backend.commands.provision import app_role_for, provision_url
from backend.tests.conftest import RUNTIME_ROLE, alembic_config


def _grants(url: str, grantee: str) -> set[tuple[str, str]]:
    engine = create_engine(url)
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT table_name, privilege_type FROM information_schema.role_table_grants "
                "WHERE grantee = :grantee"
            ),
            {"grantee": grantee},
        ).all()
    engine.dispose()
    return set(rows)


def _members(url: str, group: str) -> set[str]:
    engine = create_engine(url)
    with engine.connect() as connection:
        rows = connection.scalars(
            text(
                "SELECT m.rolname FROM pg_auth_members a JOIN pg_roles g ON g.oid = a.roleid "
                "JOIN pg_roles m ON m.oid = a.member WHERE g.rolname = :g AND NOT a.admin_option"
            ),
            {"g": group},
        )
        members = set(rows)
    engine.dispose()
    return members


def test_the_app_group_role_only_reads_the_registry(migrated_url):
    """Privileges belong to the database's group role; the login holds none itself."""
    command.upgrade(alembic_config(migrated_url), "head")
    group = app_role_for(make_url(migrated_url).database)
    assert _grants(migrated_url, group) == {("tenants", "SELECT"), ("tenant_domains", "SELECT")}
    assert _grants(migrated_url, RUNTIME_ROLE) == set()


def test_rotating_the_app_login_moves_access(migrated_url):
    """Changing DATABASE_RUNTIME_ROLE is a re-run of provisioning, not a migration."""
    command.upgrade(alembic_config(migrated_url), "head")
    group = app_role_for(make_url(migrated_url).database)
    rotated = RUNTIME_ROLE + "_rotated"
    local_db.create_runtime_role(rotated)

    assert provision_url(migrated_url, RUNTIME_ROLE) == [f"{RUNTIME_ROLE} added to {group}"]
    assert provision_url(migrated_url, RUNTIME_ROLE) == []  # repeatable
    assert provision_url(migrated_url, rotated) == [
        f"{rotated} added to {group}",
        f"{RUNTIME_ROLE} removed from {group}",
    ]

    def can_read_registry(login: str) -> bool:
        engine = create_engine(make_url(migrated_url).set(username=login))
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT count(*) FROM tenants"))
            return True
        except ProgrammingError:
            return False
        finally:
            engine.dispose()

    assert can_read_registry(rotated)
    assert not can_read_registry(RUNTIME_ROLE)


def test_a_failed_rotation_changes_nothing(migrated_url, monkeypatch):
    """The new login is never left with access alongside the old one."""
    command.upgrade(alembic_config(migrated_url), "head")
    group = app_role_for(make_url(migrated_url).database)
    rotated = RUNTIME_ROLE + "_rotated"
    local_db.create_runtime_role(rotated)
    provision_url(migrated_url, RUNTIME_ROLE)

    real_execute = psycopg.Connection.execute

    def fail_on_revoke(self, query, *args, **kwargs):
        if "REVOKE" in str(getattr(query, "as_string", lambda _c: query)(self)):
            raise RuntimeError("interrupted before the old login was removed")
        return real_execute(self, query, *args, **kwargs)

    monkeypatch.setattr(psycopg.Connection, "execute", fail_on_revoke)
    with pytest.raises(RuntimeError, match="interrupted"):
        provision_url(migrated_url, rotated)
    monkeypatch.undo()
    assert _members(migrated_url, group) == {RUNTIME_ROLE}  # the grant was rolled back


def test_provisioning_refuses_logins_that_bypass_isolation(migrated_url):
    command.upgrade(alembic_config(migrated_url), "head")
    owner = make_url(migrated_url).username or getpass.getuser()  # a superuser locally
    bypass = RUNTIME_ROLE + "_bypass"
    local_db.create_runtime_role(bypass)
    engine = create_engine(migrated_url)
    with engine.begin() as connection:
        connection.execute(text(f'ALTER ROLE "{bypass}" BYPASSRLS'))
    engine.dispose()

    for login in (owner, bypass):
        with pytest.raises(SystemExit, match="running migrations|bypass row-level security"):
            provision_url(migrated_url, login)
    assert _members(migrated_url, app_role_for(make_url(migrated_url).database)) == set()


def test_provisioning_refuses_a_login_that_owns_tables(migrated_url):
    """Like Cloud SQL's migration login: not a superuser, but owner of the tables,
    so it could alter or drop the isolation policies."""
    command.upgrade(alembic_config(migrated_url), "head")
    owner_like = RUNTIME_ROLE + "_owner"
    local_db.create_runtime_role(owner_like)
    engine = create_engine(migrated_url)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE owned_by_login (id int)"))
        connection.execute(text(f'ALTER TABLE owned_by_login OWNER TO "{owner_like}"'))
    engine.dispose()
    with pytest.raises(SystemExit, match="owns application tables"):
        provision_url(migrated_url, owner_like)


@pytest.mark.parametrize("power", ["BYPASSRLS", "owns a table"])
def test_provisioning_refuses_a_login_that_can_switch_into_a_powerful_role(migrated_url, power):
    """Checked through the whole membership graph: SET ROLE would hand these over."""
    command.upgrade(alembic_config(migrated_url), "head")
    login = RUNTIME_ROLE + "_member"
    powerful = "arqproj_test_powerful"
    local_db.create_runtime_role(login)
    engine = create_engine(migrated_url)
    with engine.begin() as connection:
        connection.execute(text(f'DROP ROLE IF EXISTS "{powerful}"'))
        connection.execute(text(f'CREATE ROLE "{powerful}" NOLOGIN'))
        if power == "BYPASSRLS":
            connection.execute(text(f'ALTER ROLE "{powerful}" BYPASSRLS'))
        else:
            connection.execute(text("CREATE TABLE owned_by_role (id int)"))
            connection.execute(text(f'ALTER TABLE owned_by_role OWNER TO "{powerful}"'))
        # Not inherited, only switchable with SET ROLE.
        connection.execute(text(f'GRANT "{powerful}" TO "{login}" WITH INHERIT FALSE, SET TRUE'))
    engine.dispose()
    try:
        with pytest.raises(SystemExit, match=f"could get around tenant isolation: {powerful}"):
            provision_url(migrated_url, login)
    finally:
        engine = create_engine(migrated_url)
        with engine.begin() as connection:
            connection.execute(text("DROP TABLE IF EXISTS owned_by_role"))
            connection.execute(text(f'DROP ROLE "{powerful}"'))
        engine.dispose()


def test_a_noinherit_login_still_gets_working_access(migrated_url):
    """Membership is granted WITH INHERIT TRUE, whatever the login's own setting."""
    command.upgrade(alembic_config(migrated_url), "head")
    login = RUNTIME_ROLE + "_noinherit"
    local_db.create_runtime_role(login)
    engine = create_engine(migrated_url)
    with engine.begin() as connection:
        connection.execute(text(f'ALTER ROLE "{login}" NOINHERIT'))
    engine.dispose()
    provision_url(migrated_url, login)

    as_login = create_engine(make_url(migrated_url).set(username=login))
    with as_login.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM tenants")) == 0  # readable
    as_login.dispose()
