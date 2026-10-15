"""Create the local development and test databases.

    uv run python -m backend.db.local setup        # create arqproj_dev and arqproj_test
    uv run python -m backend.db.local drop-test    # drop arqproj_test (tests recreate it)

Only ever touches PostgreSQL on this machine.
"""

from __future__ import annotations

import os
import sys

import psycopg
from psycopg import sql
from sqlalchemy import text
from sqlalchemy.engine import make_url

DEV_DATABASE = "arqproj_dev"
TEST_DATABASE = "arqproj_test"
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
# Connection options that can name a destination other than the URL's host part.
_HOST_OPTIONS = ("host", "hostaddr")


def _is_local(host: str) -> bool:
    # A path is a Unix socket on this machine.
    return host in LOCAL_HOSTS or host.startswith("/")


def effective_hosts(url: str) -> list[str]:
    """Every destination the driver could connect to for this URL.

    libpq takes the destination from the URL's host, but `?host=` and `?hostaddr=`
    override it, a `?service=` (or PGSERVICE) names an entry in a settings file
    that can point anywhere, and with no host at all PGHOST/PGHOSTADDR decide.
    An empty list means the default local Unix socket.
    """
    parsed = make_url(url)
    if "service" in parsed.query or os.environ.get("PGSERVICE"):
        raise SystemExit("Refusing a database service name: it can point to any server")
    hosts: list[str] = []
    for option in _HOST_OPTIONS:
        values = parsed.query.get(option) or ()
        for value in (values,) if isinstance(values, str) else values:
            hosts += value.split(",")
    if parsed.host:
        hosts += parsed.host.split(",")
    if not hosts:
        for variable in ("PGHOST", "PGHOSTADDR"):
            if os.environ.get(variable):
                hosts += os.environ[variable].split(",")
    return [host.strip() for host in hosts if host.strip()]


def require_local(url: str) -> None:
    """Refuse anything that could reach a database not on this machine."""
    remote = [host for host in effective_hosts(url) if not _is_local(host)]
    if remote:
        raise SystemExit(f"Refusing to use a non-local database host: {', '.join(remote)}")


async def require_local_server(connection) -> None:
    """Second check, once connected: ask the server where it actually is.

    `inet_server_addr()` is NULL over a Unix socket, otherwise the address the
    server answered on; anything but loopback means we reached another machine.
    """
    address = await connection.scalar(text("SELECT host(inet_server_addr())"))
    if address not in (None, "127.0.0.1", "::1"):
        raise SystemExit(f"Refusing to use a database server at {address}")


def _admin_connection() -> psycopg.Connection:
    return psycopg.connect("host=localhost port=5432 dbname=postgres", autocommit=True)


def create_database(name: str) -> bool:
    """Create the database if missing. Returns True if it was created."""
    with _admin_connection() as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone()
        if exists:
            return False
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        return True


def drop_database(name: str) -> None:
    with _admin_connection() as conn:
        conn.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
        )


def main(argv: list[str]) -> int:
    command = argv[0] if argv else "setup"
    if command == "setup":
        for name in (DEV_DATABASE, TEST_DATABASE):
            print(f"{name}: {'created' if create_database(name) else 'already exists'}")
        print("Next: uv run alembic -c backend/alembic.ini upgrade head")
        return 0
    if command == "drop-test":
        drop_database(TEST_DATABASE)
        print(f"{TEST_DATABASE}: dropped")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
