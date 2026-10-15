import json
import logging

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.settings import Settings


def client_for(environment: str) -> TestClient:
    return TestClient(create_app(Settings(environment=environment)))


def test_health_answers():
    response = client_for("test").get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_unknown_paths_are_not_found():
    assert client_for("test").get("/nothing-here").status_code == 404


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
    create_app(Settings(environment="production"))
    logging.getLogger("backend.test").warning("Olá, %s", "escritório")
    line = capsys.readouterr().out.strip().splitlines()[-1]
    assert json.loads(line) == {
        "severity": "WARNING",
        "message": "Olá, escritório",
        "logger": "backend.test",
    }


def test_local_logs_are_plain_text(capsys):
    create_app(Settings(environment="local"))
    logging.getLogger("backend.test").info("ready")
    assert capsys.readouterr().out.strip().endswith("INFO backend.test: ready")


def test_uvicorn_factory_builds_with_defaults(monkeypatch):
    # `uvicorn backend.app:create_app --factory` calls it without arguments.
    for name in ("ENVIRONMENT", "LOG_LEVEL", "K_SERVICE"):
        monkeypatch.delenv(name, raising=False)
    assert TestClient(create_app()).get("/health").status_code == 200
