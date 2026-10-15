"""Local development and test databases. Only ever touches PostgreSQL on this machine.

uv run python -m backend.commands.local_db setup       # arqproj_dev, arqproj_test, arqproj_app
uv run python -m backend.commands.local_db drop-test   # drop arqproj_test (tests recreate it)
"""

from __future__ import annotations

import sys

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

from backend.commands.provision import app_role_for
from backend.settings import LOCAL_RUNTIME_ROLE

DEV_DATABASE = "arqproj_dev"
TEST_DATABASE = "arqproj_test"


def require_local_server(url: str) -> None:
    """Connect with exactly this URL and refuse unless the server is on this machine.

    Run it before writing anything (migrations, seed data, test fixtures). Asking
    the server where it is, rather than parsing the URL, covers every way the
    driver could pick a destination: URL options, PG* environment variables,
    service files. `inet_server_addr()` is NULL over a Unix socket.
    """
    plain = make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(plain, connect_timeout=5) as conn:
        address = conn.execute("SELECT host(inet_server_addr())").fetchone()[0]
    if address not in (None, "127.0.0.1", "::1"):
        raise SystemExit(f"Refusing to use a database server at {address}")


def _admin_connection() -> psycopg.Connection:
    # Creates and drops databases, before any URL can be checked, so every
    # destination parameter is given explicitly: no PG* environment variable or
    # service file can redirect it. Both loopback addresses, for IPv6-only servers.
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
    """Drop the database and its app group role. Roles belong to the whole server,
    so the role would otherwise outlive the database, members included."""
    with _admin_connection() as conn:
        conn.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
        )
        conn.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(app_role_for(name))))


def main(argv: list[str]) -> int:
    command = argv[0] if argv else "setup"
    if command == "setup":
        for name in (DEV_DATABASE, TEST_DATABASE):
            print(f"{name}: {'created' if create_database(name) else 'already exists'}")
        role = LOCAL_RUNTIME_ROLE
        print(f"role {role}: {'created' if create_runtime_role(role) else 'already exists'}")
        print("Next: uv run alembic -c backend/alembic.ini upgrade head")
        print("Then: uv run python -m backend.commands.provision")
        return 0
    if command == "drop-test":
        drop_database(TEST_DATABASE)
        print(f"{TEST_DATABASE}: dropped")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
