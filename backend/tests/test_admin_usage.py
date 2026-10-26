"""Usage is tenant-scoped, content-free and file scans are explicitly requested."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from backend.storage.base import FOLDER_TYPE, StorageError, StorageItem, StorageProblem
from backend.storage.memory import MemoryStorage
from backend.tests import test_admin
from backend.tests.test_admin import UNIO, sign_in
from backend.web import admin

operators = test_admin.operators

pytestmark = pytest.mark.anyio


async def test_usage_excludes_deleted_projects_and_counts_filled_details(
    client, operators, db_session
):
    await sign_in(client)
    before = (await client.get("/api/admin/offices/alinea", headers=UNIO)).json()
    assert before["usage"]["projects"] == sum(before["projects"].values())
    assert before["usage"]["details"] >= before["usage"]["projects_with_details"]
    await db_session.execute(
        text(
            "UPDATE projects SET deleted_at=now() "
            "WHERE tenant_id=(SELECT id FROM tenants WHERE slug='alinea')"
        )
    )
    after = (await client.get("/api/admin/offices/alinea", headers=UNIO)).json()
    assert after["usage"]["projects"] == after["usage"]["details"] == after["usage"]["stages"] == 0
    norte = (await client.get("/api/admin/offices/norte", headers=UNIO)).json()
    assert norte["usage"]["projects"] > 0


async def test_file_scan_is_explicit_scoped_and_never_returns_names(
    client, operators, db_session, monkeypatch
):
    headers = await sign_in(client)
    now = datetime.now(UTC)
    storage = MemoryStorage()
    tenant = await db_session.scalar(text("SELECT id FROM tenants WHERE slug='alinea'"))
    project = await db_session.scalar(
        text("SELECT id FROM projects WHERE tenant_id=:t LIMIT 1"), {"t": tenant}
    )
    await db_session.execute(
        text("UPDATE projects SET folder_id='project' WHERE id=:p"), {"p": project}
    )
    await db_session.execute(
        text("UPDATE project_stages SET folder_id=NULL WHERE project_id=:p"), {"p": project}
    )
    await db_session.execute(
        text("UPDATE project_stages SET folder_id='stage' WHERE project_id=:p AND position=1"),
        {"p": project},
    )
    # Another project's folder was deleted from Drive: it has no files, and the
    # scan still completes.
    await db_session.execute(
        text("UPDATE projects SET folder_id='gone' WHERE tenant_id=:t AND id<>:p"),
        {"t": tenant, "p": project},
    )
    # Seeded files of another tenant must never be listed.
    calls = []

    async def list_folder(folder):
        calls.append(folder)
        if folder == "gone":
            raise StorageError(StorageProblem.NOT_FOUND)
        if folder == "project":
            return [StorageItem("stage", "Etapa privada", FOLDER_TYPE, None, now)]
        if folder == "stage":
            return [
                StorageItem("f1", "Segredo v1.PDF", "application/pdf", 42, now),
                StorageItem("f2", "Segredo v2.PDF", "application/pdf", 58, now),
                StorageItem("f3", "Modelo.RVT", "application/octet-stream", 200, now),
                StorageItem(
                    "f4", "Texto privado", "application/vnd.google-apps.document", None, now
                ),
            ]
        return []

    storage.list_folder = list_folder

    async def reader(*args):
        return storage

    monkeypatch.setattr(admin, "_storage", reader)
    await client.get("/api/admin/offices/alinea", headers=UNIO)
    assert calls == []
    path = "/api/admin/offices/alinea/file-statistics"
    assert (await client.post(path, headers=UNIO)).status_code == 403
    response = await client.post(path, headers=headers)
    assert response.status_code == 200, response.text
    result = response.json()
    assert (result["files"], result["known_bytes"], result["unknown_sizes"]) == (4, 300, 1)
    assert {row["kind"] for row in result["types"]} == {"pdf", "rvt", "google"}
    assert "Segredo" not in response.text and "privado" not in response.text
    assert response.headers["cache-control"] == "private, no-store"

    async def broken(*args):
        raise StorageError(StorageProblem.UNAVAILABLE, "private provider detail")

    storage.list_folder = broken
    failed = await client.post(path, headers=headers)
    assert failed.status_code == 503 and "private provider detail" not in failed.text
    assert "x-request-id" in failed.headers
    assert (
        await client.post("/api/admin/offices/unknown/file-statistics", headers=headers)
    ).status_code == 404
    assert (
        await client.post(path, headers=headers | {"host": "alinea.localhost"})
    ).status_code == 404
