"""The rules the database itself enforces for offices and their addresses."""

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from backend.tenancy.models import Tenant, TenantDomain

pytestmark = pytest.mark.anyio


async def add_office(session, slug="alinea", name="ALINEA ARQUITETOS", hosts=()):
    tenant = Tenant(slug=slug, name=name)
    session.add(tenant)
    for hostname, primary in hosts:
        session.add(TenantDomain(tenant=tenant, hostname=hostname, is_primary=primary))
    await session.flush()
    return tenant


async def assert_refused(session, coroutine, constraint):
    with pytest.raises(IntegrityError, match=constraint):
        await coroutine
    await session.rollback()


async def test_office_gets_an_id_and_timestamps(db_session):
    tenant = await add_office(db_session, hosts=[("alineaarquitetos.com", True)])
    await db_session.refresh(tenant)
    assert tenant.id is not None
    assert tenant.created_at.tzinfo is not None
    assert tenant.updated_at >= tenant.created_at


async def test_updated_at_moves_on_every_change(db_session):
    tenant = await add_office(db_session)
    await db_session.refresh(tenant)
    before = tenant.updated_at
    # A raw statement on purpose: the trigger must cover changes made outside the ORM.
    await db_session.execute(
        text("UPDATE tenants SET name = 'Alinea' WHERE id = :id"), {"id": tenant.id}
    )
    await db_session.refresh(tenant)
    assert tenant.name == "Alinea"
    assert tenant.updated_at > before


async def test_a_hostname_belongs_to_one_office_only(db_session):
    await add_office(db_session, "alinea", hosts=[("alineaarquitetos.com", True)])
    await assert_refused(
        db_session,
        add_office(db_session, "outra", "Outra", hosts=[("alineaarquitetos.com", True)]),
        "uq_tenant_domains_hostname",
    )


async def test_one_primary_address_per_office(db_session):
    await add_office(
        db_session, hosts=[("alineaarquitetos.com", True), ("alinea.example.com", False)]
    )
    # Another office can have its own primary address.
    await add_office(db_session, "outra", "Outra", hosts=[("outra.example.com", True)])
    tenant = (await db_session.scalars(select(Tenant).where(Tenant.slug == "alinea"))).one()
    db_session.add(TenantDomain(tenant=tenant, hostname="old.example.com", is_primary=True))
    await assert_refused(db_session, db_session.flush(), "uq_tenant_domains_one_primary")


@pytest.mark.parametrize(
    ("hostname", "constraint"),
    [
        ("AlineaArquitetos.com", "hostname_format"),
        ("alineaarquitetos.com:443", "hostname_format"),
        ("alineaarquitetos.com.", "hostname_format"),
        ("https://alineaarquitetos.com", "hostname_format"),
    ],
)
async def test_hostnames_are_stored_normalised(db_session, hostname, constraint):
    await assert_refused(db_session, add_office(db_session, hosts=[(hostname, True)]), constraint)


@pytest.mark.parametrize(
    ("values", "constraint"),
    [
        ({"slug": "Alinea Arquitetos"}, "ck_tenants_slug_format"),
        ({"slug": "-alinea"}, "ck_tenants_slug_format"),
        ({"name": "   "}, "ck_tenants_name_not_blank"),
        ({"status": "deleted"}, "ck_tenants_status_known"),
    ],
)
async def test_office_values_are_checked(db_session, values, constraint):
    fields = {"slug": "alinea", "name": "ALINEA ARQUITETOS"} | values
    db_session.add(Tenant(**fields))
    await assert_refused(db_session, db_session.flush(), constraint)


async def test_slugs_are_unique(db_session):
    await add_office(db_session, "alinea")
    await assert_refused(db_session, add_office(db_session, "alinea", "Outra"), "uq_tenants_slug")


async def test_removing_an_office_removes_its_addresses(db_session):
    tenant = await add_office(db_session, hosts=[("alineaarquitetos.com", True)])
    await db_session.execute(text("DELETE FROM tenants WHERE id = :id"), {"id": tenant.id})
    remaining = await db_session.scalar(text("SELECT count(*) FROM tenant_domains"))
    assert remaining == 0
