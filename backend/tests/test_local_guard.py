"""The check that keeps tests and local commands away from any non-local database."""

import pytest
from sqlalchemy.engine import make_url

from backend.commands import local_db


class _FakeServer:
    """Stands in for psycopg.connect: a server answering from `address`."""

    def __init__(self, address):
        self.address = address
        self.dsn = None

    def connect(self, dsn, **kwargs):
        self.dsn = dsn
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, query):
        assert "inet_server_addr" in query
        return self

    def fetchone(self):
        return (self.address,)


def test_our_local_server_passes(test_database_url):
    local_db.require_local_server(test_database_url)


@pytest.mark.parametrize("address", ["203.0.113.7", "10.0.0.5", "2001:db8::1"])
def test_a_server_on_another_machine_is_refused(monkeypatch, address):
    # Whatever sent us there (URL options, PG* variables, a service file), the
    # server's own address is what is checked.
    monkeypatch.setattr(local_db.psycopg, "connect", _FakeServer(address).connect)
    with pytest.raises(SystemExit, match=address):
        local_db.require_local_server("postgresql+psycopg://localhost/arqproj_test")


@pytest.mark.parametrize("address", [None, "127.0.0.1", "::1"])  # None: Unix socket
def test_loopback_and_sockets_pass(monkeypatch, address):
    monkeypatch.setattr(local_db.psycopg, "connect", _FakeServer(address).connect)
    local_db.require_local_server("postgresql+psycopg://localhost/arqproj_test")


def test_the_check_connects_with_exactly_the_given_url(monkeypatch):
    server = _FakeServer("127.0.0.1")
    monkeypatch.setattr(local_db.psycopg, "connect", server.connect)
    local_db.require_local_server("postgresql+psycopg://me@localhost:5432/x?host=/tmp")
    used = make_url(server.dsn)
    assert (used.username, used.host, used.port, used.database) == ("me", "localhost", 5432, "x")
    assert used.query == {"host": "/tmp"}  # options are passed on, not dropped


def test_the_admin_connection_ignores_a_hostile_environment(monkeypatch, test_database_url):
    # Databases are created before any URL can be checked, so this connection must
    # not be redirectable. Honouring these variables would dial 203.0.113.7.
    monkeypatch.setenv("PGHOSTADDR", "203.0.113.7")
    monkeypatch.setenv("PGHOST", "db.example.com")
    with local_db._admin_connection() as conn:
        assert conn.info.hostaddr in ("127.0.0.1", "::1")
