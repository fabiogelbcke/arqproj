"""Is a login safe to run the app as? Used at app startup and by provisioning.

Office isolation (row-level security) only binds a login that cannot get around
it. A login fails this check if it, or any role it can reach (as a member, by
inheritance, or with SET ROLE, directly or indirectly), is a superuser, has
BYPASSRLS, or owns application tables (owners can alter or drop the policies;
Cloud SQL's migration login is such an owner without being a superuser).
"""

from __future__ import annotations

_PROBLEMS = """
SELECT r.rolname,
       r.rolsuper,
       r.rolbypassrls,
       EXISTS (SELECT 1 FROM pg_class c
               WHERE c.relowner = r.oid AND c.relnamespace = 'public'::regnamespace)
FROM pg_roles r
WHERE (pg_has_role({login}, r.oid, 'MEMBER')
       OR pg_has_role({login}, r.oid, 'USAGE')
       OR pg_has_role({login}, r.oid, 'SET'))
  AND (r.rolsuper OR r.rolbypassrls
       OR EXISTS (SELECT 1 FROM pg_class c
                  WHERE c.relowner = r.oid AND c.relnamespace = 'public'::regnamespace))
ORDER BY r.rolname
"""
# The same query for the two drivers' parameter styles.
PROBLEMS_SQL_PSYCOPG = _PROBLEMS.format(login="%(login)s")
PROBLEMS_SQL_SQLALCHEMY = _PROBLEMS.format(login=":login")


def describe(problems: list[tuple]) -> str:
    """Readable reasons, e.g. 'arqproj_app via admin_role: can bypass row-level security'."""
    reasons = []
    for name, superuser, bypassrls, owns_tables in problems:
        what = [
            label
            for flag, label in (
                (superuser, "superuser"),
                (bypassrls, "can bypass row-level security"),
                (owns_tables, "owns application tables"),
            )
            if flag
        ]
        reasons.append(f"{name}: {', '.join(what)}")
    return "; ".join(reasons)
