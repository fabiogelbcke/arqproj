"""The guard that keeps tests and local commands away from any non-local database."""

import pytest

from backend.db import local

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
def no_libpq_environment(monkeypatch):
    for name in ("PGHOST", "PGHOSTADDR", "PGSERVICE"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://localhost:5432/arqproj_test",
        "postgresql+psycopg://127.0.0.1/arqproj_test",
        "postgresql+psycopg://[::1]/arqproj_test",
        "postgresql+psycopg:///arqproj_test",  # default local socket
        "postgresql+psycopg:///arqproj_test?host=/tmp",  # explicit local socket
        "postgresql+psycopg://localhost/arqproj_test?host=localhost",
    ],
)
def test_local_destinations_are_allowed(url):
    local.require_local(url)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://db.example.com/portal",
        # Options that override the host part (the reported bypass):
        "postgresql+psycopg://localhost/arqproj_test?host=db.example.com",
        "postgresql+psycopg://localhost/arqproj_test?hostaddr=10.0.0.5",
        "postgresql+psycopg://localhost/arqproj_test?host=localhost,db.example.com",
        # A service entry can point anywhere:
        "postgresql+psycopg:///arqproj_test?service=prod",
    ],
)
def test_remote_destinations_are_refused(url):
    with pytest.raises(SystemExit, match="Refusing"):
        local.require_local(url)


@pytest.mark.parametrize(
    ("variable", "value"),
    [("PGHOST", "db.example.com"), ("PGHOSTADDR", "10.0.0.5"), ("PGSERVICE", "prod")],
)
def test_environment_overrides_are_refused(monkeypatch, variable, value):
    monkeypatch.setenv(variable, value)
    with pytest.raises(SystemExit, match="Refusing"):
        local.require_local("postgresql+psycopg:///arqproj_test")


def test_pghost_does_not_matter_when_the_url_names_a_local_host(monkeypatch):
    # libpq only falls back to PGHOST when the URL gives no host.
    monkeypatch.setenv("PGHOST", "db.example.com")
    local.require_local("postgresql+psycopg://localhost/arqproj_test")


def test_pghostaddr_is_refused_even_when_the_url_names_localhost(monkeypatch):
    # hostaddr is filled independently of host: libpq would dial this address.
    monkeypatch.setenv("PGHOSTADDR", "203.0.113.7")
    with pytest.raises(SystemExit, match="203.0.113.7"):
        local.require_local("postgresql+psycopg://localhost/arqproj_test")


def test_an_explicit_local_hostaddr_wins_over_the_environment(monkeypatch):
    monkeypatch.setenv("PGHOSTADDR", "203.0.113.7")
    local.require_local("postgresql+psycopg://localhost/arqproj_test?hostaddr=127.0.0.1")


def test_the_admin_connection_ignores_a_hostile_environment(monkeypatch, test_database_url):
    # Database creation runs before any post-connect check, so its own connection
    # must not be redirectable. With PGHOSTADDR honoured this would try 203.0.113.7.
    monkeypatch.setenv("PGHOSTADDR", "203.0.113.7")
    monkeypatch.setenv("PGHOST", "db.example.com")
    with local._admin_connection() as conn:
        assert conn.info.hostaddr == "127.0.0.1"


async def test_the_connected_server_is_checked_too(db_connection):
    await local.require_local_server(db_connection)  # our real local test server


async def test_a_remote_server_is_refused_after_connecting():
    class RemoteServer:
        async def scalar(self, statement):
            assert "inet_server_addr" in str(statement)
            return "203.0.113.7"

    with pytest.raises(SystemExit, match="203.0.113.7"):
        await local.require_local_server(RemoteServer())
