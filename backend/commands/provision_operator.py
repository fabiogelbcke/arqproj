"""Provision the separate operator login. Run with the migration owner's access.

Local: uv run python -m backend.commands.provision_operator --login arqproj_operator --local
Deployed: set MIGRATION_DATABASE_URL and pass the pre-created IAM login with --login.
Never grant the operator group to the ordinary app login.
"""

import argparse

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

from backend.commands import local_db
from backend.commands.provision import _refuse_unsafe_login
from backend.settings import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--login", required=True)
    parser.add_argument("--local", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    if args.login == settings.database_runtime_role:
        raise SystemExit("Operator and app logins must be separate")
    if args.local:
        local_db.require_local_server(settings.migration_database_url)
        local_db.create_runtime_role(args.login)
    provision_url(settings.migration_database_url, args.login)
    print("Operator login provisioned.")


def provision_url(owner_url: str, login: str) -> None:
    url = make_url(owner_url).set(drivername="postgresql")
    with psycopg.connect(url.render_as_string(hide_password=False)) as conn:
        _refuse_unsafe_login(conn, login)
        group = conn.execute("SELECT current_database() || '_operator'").fetchone()[0]
        if conn.execute(
            "SELECT pg_has_role(%s, current_database() || '_app', 'MEMBER')", (login,)
        ).fetchone()[0]:
            raise SystemExit("Operator login must not also be an app login")
        conn.execute(
            sql.SQL("GRANT {} TO {} WITH INHERIT TRUE").format(
                sql.Identifier(group), sql.Identifier(login)
            )
        )


if __name__ == "__main__":
    main()
