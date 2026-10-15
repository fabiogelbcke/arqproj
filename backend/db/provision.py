"""Give the app's login its privileges, by membership of the database's group role.

    uv run python -m backend.db.provision

Run after migrations (locally, and as a release step when deployed). Connects as
the owner (MIGRATION_DATABASE_URL) and makes DATABASE_RUNTIME_ROLE the one member
of `<database>_app`, removing any other login. Safe to run repeatedly; changing
the login (for example rotating a service account) is a re-run, not a migration.
"""

from __future__ import annotations

import sys

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

from backend.settings import Settings


def app_role_for(database: str) -> str:
    """The group role holding the app's privileges in a database (created by
    migration 0002 as `current_database() || '_app'`)."""
    return f"{database}_app"


def _refuse_unsafe_login(conn: psycopg.Connection, login: str) -> None:
    """The app's login must be subject to row-level security, or isolation is void."""
    role = conn.execute(
        "SELECT rolsuper, rolbypassrls, rolname = current_user FROM pg_roles WHERE rolname = %s",
        (login,),
    ).fetchone()
    if role is None:
        raise SystemExit(f"Login {login} does not exist: create it first")
    superuser, bypassrls, is_runner = role
    if superuser or bypassrls:
        # Exempt from row-level security even when it is FORCEd.
        raise SystemExit(f"Login {login} is a superuser or can bypass row-level security")
    if is_runner:
        raise SystemExit(f"Login {login} is the login running migrations and provisioning")
    # Owners can ALTER or DROP the policies on their tables. Cloud SQL has no true
    # superuser, so its migration login passes the check above yet owns everything.
    owned = conn.execute(
        "SELECT c.relname FROM pg_class c JOIN pg_roles r ON r.oid = c.relowner "
        "WHERE c.relnamespace = 'public'::regnamespace AND r.rolname = %s LIMIT 1",
        (login,),
    ).fetchone()
    if owned:
        raise SystemExit(f"Login {login} owns application tables (e.g. {owned[0]})")


def provision(conn: psycopg.Connection, login: str) -> list[str]:
    """Make `login` the only member of this database's app role. Returns changes.

    Runs inside one transaction (see `provision_url`): a rotation either fully
    happens or not at all, never leaving the old and new logins both with access.
    """
    database = conn.execute("SELECT current_database()").fetchone()[0]
    group = app_role_for(database)
    if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (group,)).fetchone():
        raise SystemExit(f"Role {group} does not exist: run migrations first")
    _refuse_unsafe_login(conn, login)

    # Ordinary members only: since PostgreSQL 16 a non-superuser who creates a role
    # (the migration login on Cloud SQL) is made an admin member of it; that link
    # administers the role and is not app access, so it is left alone.
    members = {
        row[0]
        for row in conn.execute(
            "SELECT m.rolname FROM pg_auth_members a "
            "JOIN pg_roles g ON g.oid = a.roleid JOIN pg_roles m ON m.oid = a.member "
            "WHERE g.rolname = %s AND NOT a.admin_option AND m.rolname <> current_user",
            (group,),
        )
    }
    changes = []
    # Inheritance stated explicitly: otherwise it follows the login's own setting,
    # and a NOINHERIT login would be "added" yet unable to use the privileges
    # (the app never runs SET ROLE). Re-granting also fixes an existing membership.
    inherits = conn.execute(
        "SELECT a.inherit_option FROM pg_auth_members a "
        "JOIN pg_roles g ON g.oid = a.roleid JOIN pg_roles m ON m.oid = a.member "
        "WHERE g.rolname = %s AND m.rolname = %s AND NOT a.admin_option",
        (group, login),
    ).fetchone()
    if inherits is None or not inherits[0]:
        conn.execute(
            sql.SQL("GRANT {} TO {} WITH INHERIT TRUE").format(
                sql.Identifier(group), sql.Identifier(login)
            )
        )
        changes.append(f"{login} added to {group}")
    for former in sorted(members - {login}):
        conn.execute(
            sql.SQL("REVOKE {} FROM {}").format(sql.Identifier(group), sql.Identifier(former))
        )
        changes.append(f"{former} removed from {group}")
    return changes


def provision_url(owner_url: str, login: str) -> list[str]:
    """`provision` for a SQLAlchemy-style owner URL (as in MIGRATION_DATABASE_URL)."""
    url = make_url(owner_url).set(drivername="postgresql")
    with psycopg.connect(url.render_as_string(hide_password=False)) as conn:
        with conn.transaction():
            return provision(conn, login)


def main() -> int:
    settings = Settings()
    changes = provision_url(settings.migration_database_url, settings.database_runtime_role)
    print("\n".join(changes) if changes else "Already provisioned.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
