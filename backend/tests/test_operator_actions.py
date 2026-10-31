"""Lifecycle mutations use the restricted operator role and audit atomically."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from backend.tests import test_admin
from backend.tests.conftest import _session_on

operators = test_admin.operators
UNIO = test_admin.UNIO
pytestmark = pytest.mark.anyio


@pytest.fixture
async def actions_enabled(app, db_connection, operators):
    class OperatorSession:
        async def __aenter__(self):
            await db_connection.exec_driver_sql('SET ROLE "arqproj_test_operator"')
            self.session = _session_on(db_connection)
            return self.session

        async def __aexit__(self, *exc):
            await self.session.close()
            await db_connection.exec_driver_sql("RESET ROLE")

    app.state.operator_sessionmaker = OperatorSession


async def test_create_owner_suspend_restore_delete_with_retained_audit(
    client, actions_enabled, db_session
):
    headers = await test_admin.sign_in(client)
    body = {"slug": "novo", "name": "Escritório Novo", "hostname": "novo.localhost"}
    created = await client.post("/api/admin/offices", json=body, headers=headers)
    assert created.status_code == 200, created.text
    assert "/painel/entrar-na-equipe#token=" in created.json()["owner_url"]
    path = "/api/admin/offices/novo/actions"
    refused = await client.post(
        path, json={"action": "delete", "confirmation": body["name"]}, headers=headers
    )
    assert refused.status_code == 409
    for action in ("owner_link", "suspend", "restore", "suspend"):
        result = await client.post(path, json={"action": action}, headers=headers)
        assert result.status_code == 200, result.text
    assert (
        await client.post(path, json={"action": "delete", "confirmation": "wrong"}, headers=headers)
    ).status_code == 409
    assert (
        await client.post(
            path, json={"action": "delete", "confirmation": body["name"]}, headers=headers
        )
    ).status_code == 200
    assert (await client.get("/api/admin/offices/novo", headers=UNIO)).status_code == 404
    assert (await client.get("/api/admin/offices/alinea", headers=UNIO)).status_code == 200
    events = (
        await db_session.execute(
            text(
                "SELECT action, actor, request_id FROM operator_audit_events "
                "WHERE target_slug='novo' ORDER BY created_at"
            )
        )
    ).all()
    assert len(events) == 6
    assert {row.action for row in events} == {
        "create",
        "owner_link",
        "suspend",
        "restore",
        "delete",
    }
    assert all(row.actor == test_admin.OPERATOR and row.request_id for row in events)


async def test_delete_populated_tenant_preserves_other_tenant(client, actions_enabled, db_session):
    headers = await test_admin.sign_in(client)
    name = await db_session.scalar(text("SELECT name FROM tenants WHERE slug='alinea'"))
    # A proposal and a service preset (A42): deleted with the office too.
    alinea = await db_session.scalar(text("SELECT id FROM tenants WHERE slug='alinea'"))
    await db_session.execute(
        text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(alinea)}
    )
    await db_session.execute(
        text(
            "INSERT INTO proposals (project_id, version, content) "
            "SELECT id, 1, '{}'::jsonb FROM projects WHERE tenant_id = :t LIMIT 1"
        ),
        {"t": str(alinea)},
    )
    await db_session.execute(
        text(
            "INSERT INTO proposal_service_presets (position, title, description) "
            "VALUES (1, 'Briefing', '')"
        )
    )
    # A portfolio drawn from a project, with a photo: deleted with the office too.
    await db_session.execute(text("INSERT INTO portfolios (published, intro) VALUES (true, '')"))
    await db_session.execute(
        text(
            "INSERT INTO portfolio_entries (position, title, place, description, project_id) "
            "SELECT 1, 'Casa', '', '', id FROM projects WHERE tenant_id = :t LIMIT 1"
        ),
        {"t": str(alinea)},
    )
    await db_session.execute(
        text(
            "INSERT INTO portfolio_photos (entry_id, position, file_id, image_type) "
            "SELECT id, 1, 'x', 'image/jpeg' FROM portfolio_entries"
        )
    )
    path = "/api/admin/offices/alinea/actions"
    assert (await client.post(path, json={"action": "suspend"}, headers=headers)).status_code == 200
    assert (
        await client.get("/api/pages/casa-jardim", headers={"host": "alinea.localhost"})
    ).status_code == 404
    result = await client.post(
        path, json={"action": "delete", "confirmation": name}, headers=headers
    )
    assert result.status_code == 200, result.text
    assert (
        await db_session.scalar(
            text(
                "SELECT count(*) FROM projects "
                "WHERE tenant_id=(SELECT id FROM tenants WHERE slug='norte')"
            )
        )
        > 0
    )
    assert (
        await db_session.scalar(
            text("SELECT count(*) FROM operator_audit_events WHERE target_slug='alinea'")
        )
        == 2
    )
    for table in (
        "proposals",
        "proposal_service_presets",
        "portfolios",
        "portfolio_entries",
        "portfolio_photos",
    ):
        left = await db_session.scalar(
            text(f"SELECT count(*) FROM {table} WHERE tenant_id = :t"), {"t": alinea}
        )
        assert left == 0, table


async def test_actions_require_operator_host_csrf_and_configuration(client, operators):
    path = "/api/admin/offices/alinea/actions"
    body = {"action": "suspend"}
    assert (await client.post(path, json=body, headers=UNIO)).status_code == 401
    headers = await test_admin.sign_in(client)
    assert (await client.post(path, json=body, headers=UNIO)).status_code == 403
    assert (
        await client.post(path, json=body, headers=headers | {"host": "alinea.localhost"})
    ).status_code == 404
    assert (await client.post(path, json=body, headers=headers)).status_code == 503


async def test_duplicate_creation_rolls_back_and_does_not_audit(
    client, actions_enabled, db_session
):
    headers = await test_admin.sign_in(client)
    response = await client.post(
        "/api/admin/offices",
        json={"slug": "alinea", "name": "Outro", "hostname": "outro.localhost"},
        headers=headers,
    )
    assert response.status_code == 409 and "INSERT" not in response.text
    assert await db_session.scalar(text("SELECT count(*) FROM operator_audit_events")) == 0


async def test_app_cannot_read_audit_and_operator_cannot_change_audit(app, actions_enabled):
    # Negative permission checks are the safety rule's executable violation cases.
    async with app.state.sessionmaker() as db:
        with pytest.raises(ProgrammingError):
            await db.execute(text("SELECT * FROM operator_audit_events"))
    async with app.state.operator_sessionmaker() as db:
        with pytest.raises(ProgrammingError):
            await db.execute(text("DELETE FROM operator_audit_events"))


async def test_failed_audit_rolls_back_action(client, actions_enabled, db_session, monkeypatch):
    from backend.operators import actions

    original = actions.audit

    def bad_audit(db, actor, action, tenant, request_id):
        original(db, None, action, tenant, request_id)  # NOT NULL violation at commit

    monkeypatch.setattr(actions, "audit", bad_audit)
    headers = await test_admin.sign_in(client)
    response = await client.post(
        "/api/admin/offices/alinea/actions", json={"action": "suspend"}, headers=headers
    )
    assert response.status_code == 409
    assert (
        await db_session.scalar(text("SELECT status FROM tenants WHERE slug='alinea'")) == "active"
    )
