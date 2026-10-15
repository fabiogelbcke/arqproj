"""Create the local development and test databases.

    uv run python -m backend.db.local setup        # create arqproj_dev and arqproj_test
    uv run python -m backend.db.local drop-test    # drop arqproj_test (tests recreate it)

Only ever touches PostgreSQL on this machine.
"""

from __future__ import annotations

import sys

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

DEV_DATABASE = "arqproj_dev"
TEST_DATABASE = "arqproj_test"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", None, ""}


def require_local(url: str) -> None:
    """Refuse anything that is not a database on this machine."""
    host = make_url(url).host
    if host not in LOCAL_HOSTS:
        raise SystemExit(f"Refusing to use a non-local database host: {host!r}")


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
