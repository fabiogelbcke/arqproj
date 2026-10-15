"""Create the local development and test databases.

    uv run python -m backend.db.local setup        # arqproj_dev, arqproj_test, arqproj_app login
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

from backend.settings import LOCAL_RUNTIME_ROLE

DEV_DATABASE = "arqproj_dev"
TEST_DATABASE = "arqproj_test"
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def _is_local(host: str) -> bool:
    # A path is a Unix socket on this machine.
    return host in LOCAL_HOSTS or host.startswith("/")


# Connection options a local URL may carry. `host` and `hostaddr` are inspected
# below; the rest cannot change where the connection goes.
_ALLOWED_OPTIONS = frozenset(
    {"host", "hostaddr", "application_name", "connect_timeout", "sslmode", "options"}
)


def _option(parsed, name: str) -> list[str]:
    values = parsed.query.get(name) or ()
    return [
        part
        for value in ((values,) if isinstance(values, str) else values)
        for part in value.split(",")
    ]


def effective_hosts(url: str) -> list[str]:
    """Every destination libpq could connect to for this URL.

    libpq fills each connection parameter independently: from the connection
    string (the URL's host, or `?host=`), or else from its environment variable.
    So `host` falls back to PGHOST only when the URL gives none, while `hostaddr`
    (the address actually dialled) comes from `?hostaddr=` or else PGHOSTADDR,
    even when the URL names localhost. A `?service=` or PGSERVICE names an entry in
    a settings file that can point anywhere, so it is refused outright. An empty
    list means the default local Unix socket.
    """
    parsed = make_url(url)
    if "service" in parsed.query or os.environ.get("PGSERVICE"):
        raise SystemExit("Refusing a database service name: it can point to any server")
    # Allowlist, not blocklist: any other option (e.g. `conninfo`, which embeds a
    # whole connection string) could carry a destination this function cannot see.
    unknown = set(parsed.query) - _ALLOWED_OPTIONS
    if unknown:
        raise SystemExit(
            f"Refusing connection options that may change the destination: {sorted(unknown)}"
        )
    hosts = _option(parsed, "host") + (parsed.host.split(",") if parsed.host else [])
    if not hosts and os.environ.get("PGHOST"):
        hosts = os.environ["PGHOST"].split(",")
    hostaddrs = _option(parsed, "hostaddr")
    if not hostaddrs and os.environ.get("PGHOSTADDR"):
        hostaddrs = os.environ["PGHOSTADDR"].split(",")
    return [host.strip() for host in hosts + hostaddrs if host.strip()]


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


def require_local_server_before_use(url: str) -> None:
    """The post-connect check, for code about to run migrations or create data:
    connect once with exactly this URL and confirm the server is on loopback."""
    require_local(url)
    plain = make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(plain, connect_timeout=5) as conn:
        address = conn.execute("SELECT host(inet_server_addr())").fetchone()[0]
    if address not in (None, "127.0.0.1", "::1"):
        raise SystemExit(f"Refusing to use a database server at {address}")


def _admin_connection() -> psycopg.Connection:
    # Every destination parameter given explicitly, so no PG* environment variable
    # or service file can redirect this connection to another machine. Both loopback
    # addresses, tried in order, so an IPv6-only local server works too.
    return psycopg.connect(
        "host=localhost,localhost hostaddr=127.0.0.1,::1 port=5432 dbname=postgres",
        autocommit=True,
    )


def create_database(name: str) -> bool:
    """Create the database if missing. Returns True if it was created."""
    with _admin_connection() as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone()
        if exists:
            return False
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        return True


def create_runtime_role(name: str) -> bool:
    """The app's restricted login: no superuser, no BYPASSRLS, owns nothing.
    Locally it needs no password (Homebrew PostgreSQL trusts local connections).
    Returns True if it was created."""
    with _admin_connection() as conn:
        if conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (name,)).fetchone():
            return False
        conn.execute(
            sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE").format(
                sql.Identifier(name)
            )
        )
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
        role = LOCAL_RUNTIME_ROLE
        print(f"role {role}: {'created' if create_runtime_role(role) else 'already exists'}")
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
