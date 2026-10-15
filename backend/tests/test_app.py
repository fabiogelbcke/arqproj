import getpass
import json
import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url

from backend.app import create_app
from backend.settings import Settings
from backend.tests.conftest import RUNTIME_ROLE, TEST_DATABASE_URL


def settings_for(environment: str) -> Settings:
    return Settings(environment=environment, database_url=TEST_DATABASE_URL)


def client_for(environment: str) -> TestClient:
    return TestClient(create_app(settings_for(environment)))


def test_health_answers():
    response = client_for("test").get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("environment", ["local", "staging"])
def test_api_docs_outside_production(environment):
    client = client_for(environment)
    assert client.get("/api/docs").status_code == 200
    assert client.get("/api/openapi.json").status_code == 200


def test_no_api_docs_in_production():
    client = client_for("production")
    assert client.get("/api/docs").status_code == 404
    assert client.get("/api/openapi.json").status_code == 404


def test_deployed_logs_are_one_json_object_per_line(capsys):
    create_app(settings_for("production"))
    logging.getLogger("backend.test").warning("Olá, %s", "escritório")
    line = capsys.readouterr().out.strip().splitlines()[-1]
    assert json.loads(line) == {
        "severity": "WARNING",
        "message": "Olá, escritório",
        "logger": "backend.test",
        "request_id": "-",  # outside a request
    }


def test_local_logs_are_plain_text(capsys):
    create_app(settings_for("local"))
    logging.getLogger("backend.test").info("ready")
    assert capsys.readouterr().out.strip().endswith("INFO backend.test [-]: ready")


def test_uvicorn_factory_builds_with_defaults(monkeypatch):
    # `uvicorn backend.app:create_app --factory` calls it without arguments.
    for name in ("ENVIRONMENT", "LOG_LEVEL", "K_SERVICE", "DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    assert TestClient(create_app()).get("/health").status_code == 200


def runtime_settings(**overrides) -> Settings:
    url = make_url(TEST_DATABASE_URL).set(username=RUNTIME_ROLE).render_as_string(False)
    return Settings(environment="test", database_url=url, **overrides)


def test_startup_opens_a_working_database_pool(test_database_url):
    app = create_app(runtime_settings())

    async def ping() -> int:
        async with app.state.sessionmaker() as session:
            return await session.scalar(text("SELECT 1"))

    with TestClient(app) as client:  # runs startup and shutdown
        assert client.portal.call(ping) == 1


def test_the_app_never_loads_migration_helpers():
    """Migration-writing SQL lives apart from runtime code; the app must not import it."""
    import subprocess
    import sys

    code = "import backend.app, sys; print('backend.migrations.snippets' in sys.modules)"
    loaded = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert loaded.stdout.strip() == "False"


def test_startup_refuses_a_login_other_than_the_checked_one(test_database_url):
    """DATABASE_URL and DATABASE_RUNTIME_ROLE disagree: the app does not serve."""
    app = create_app(runtime_settings(database_runtime_role="someone_else"))
    with pytest.raises(RuntimeError, match="DATABASE_RUNTIME_ROLE"), TestClient(app):
        pass


def test_startup_refuses_a_login_that_could_get_around_isolation(test_database_url):
    """Even when both settings name it: the owner (a superuser locally) is refused."""
    owner = make_url(TEST_DATABASE_URL).username or getpass.getuser()
    app = create_app(
        Settings(environment="test", database_url=TEST_DATABASE_URL, database_runtime_role=owner)
    )
    with pytest.raises(RuntimeError, match="could get around office isolation"), TestClient(app):
        pass
