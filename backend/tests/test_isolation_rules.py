"""Schema rules that keep every tenant table isolated, now and in future migrations.

Each rule has a self-test showing it catches a violation, so it cannot silently
stop working.
"""

import pytest
from alembic import command
from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.db.isolation import TenantOwned
from backend.migrations.registry import metadata
from backend.migrations.snippets import (
    POLICY,
    REGISTRY_TABLES,
    enable_tenant_isolation_sql,
)
from backend.tests.conftest import (
    alembic_config,
    build_from_models,
)

_REQUIRED_POLICY = (
    POLICY,
    "PERMISSIVE",
    "{public}",
    "ALL",
    "(tenant_id = current_tenant_id())",
    "(tenant_id = current_tenant_id())",
)


def _unisolated_tenant_tables(url: str) -> set[str]:
    """Tables with a tenant_id that lack enforced row-level security, the exact
    policy (and no other), or the default that fills tenant_id with the tenant."""
    engine = create_engine(url)
    with engine.connect() as connection:
        tables = connection.execute(
            text(
                """
                SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
                       col.column_default = 'current_tenant_id()'
                FROM pg_class c
                JOIN information_schema.columns col
                  ON col.table_name = c.relname AND col.column_name = 'tenant_id'
                WHERE c.relnamespace = 'public'::regnamespace AND c.relkind = 'r'
                """
            )
        ).all()
        policies: dict[str, list[tuple]] = {}
        for table, *policy in connection.execute(
            text(
                "SELECT tablename, policyname, permissive, roles::text, cmd, qual, with_check "
                "FROM pg_policies WHERE schemaname = 'public'"
            )
        ):
            policies.setdefault(table, []).append(tuple(policy))
    engine.dispose()
    return {
        name
        for name, enabled, forced, has_default in tables
        if name not in REGISTRY_TABLES
        and not (enabled and forced and has_default and policies.get(name) == [_REQUIRED_POLICY])
    }


def test_every_tenant_table_is_isolated(migrated_url):
    """Any future table holding tenant data must turn on row-level security."""
    command.upgrade(alembic_config(migrated_url), "head")
    assert _unisolated_tenant_tables(migrated_url) == set()


def test_the_isolation_rule_catches_a_forgotten_table(migrated_url):
    command.upgrade(alembic_config(migrated_url), "head")
    engine = create_engine(migrated_url)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE forgotten (id int, tenant_id uuid)"))
    engine.dispose()
    assert _unisolated_tenant_tables(migrated_url) == {"forgotten"}


def test_the_isolation_rule_catches_a_missing_default(migrated_url):
    """Isolated, but tenant_id would have to be set by hand: flagged too."""
    command.upgrade(alembic_config(migrated_url), "head")
    engine = create_engine(migrated_url)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE no_default (id int, tenant_id uuid)"))
        for statement in enable_tenant_isolation_sql("no_default"):
            connection.execute(text(statement))
        connection.execute(text("ALTER TABLE no_default ALTER COLUMN tenant_id DROP DEFAULT"))
    engine.dispose()
    assert _unisolated_tenant_tables(migrated_url) == {"no_default"}


@pytest.mark.parametrize(
    "weaken",
    [
        # The right name, but everything visible:
        "ALTER POLICY tenant_isolation ON weak USING (true)",
        # The right policy, plus a second one that ORs in more rows:
        "CREATE POLICY extra ON weak USING (true)",
        # Reads isolated, writes not checked:
        "ALTER POLICY tenant_isolation ON weak WITH CHECK (true)",
    ],
)
def test_the_isolation_rule_checks_what_the_policy_does(migrated_url, weaken):
    """Self-test: a policy that is named right but weaker is still flagged."""
    command.upgrade(alembic_config(migrated_url), "head")
    engine = create_engine(migrated_url)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE weak (id int, tenant_id uuid)"))
        for statement in enable_tenant_isolation_sql("weak"):
            connection.execute(text(statement))
    engine.dispose()
    assert _unisolated_tenant_tables(migrated_url) == set()  # correct as created

    engine = create_engine(migrated_url)
    with engine.begin() as connection:
        connection.execute(text(weaken))
    engine.dispose()
    assert _unisolated_tenant_tables(migrated_url) == {"weak"}


def test_tenant_owned_models_default_to_the_current_tenant(migrated_url):
    """A model using TenantOwned builds the same column a migration would."""
    sample = MetaData(naming_convention=metadata.naming_convention)

    class SampleBase(DeclarativeBase):
        metadata = sample

    metadata.tables["tenants"].to_metadata(sample)

    class Sample(TenantOwned, SampleBase):
        __tablename__ = "sample_tenant_rows"
        id: Mapped[int] = mapped_column(primary_key=True)

    build_from_models(migrated_url, sample)
    engine = create_engine(migrated_url)
    with engine.connect() as connection:
        default, nullable = connection.execute(
            text(
                "SELECT column_default, is_nullable FROM information_schema.columns "
                "WHERE table_name = 'sample_tenant_rows' AND column_name = 'tenant_id'"
            )
        ).one()
    engine.dispose()
    assert (default, nullable) == ("current_tenant_id()", "NO")
