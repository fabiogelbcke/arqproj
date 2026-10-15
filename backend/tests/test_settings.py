import pytest
from pydantic import ValidationError

from backend.settings import Environment, Settings

DB = "postgresql+psycopg://db.internal:5432/portal"


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    """Each test starts without the variables these settings read."""
    for name in ("ENVIRONMENT", "LOG_LEVEL", "K_SERVICE", "DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)


def test_without_settings_it_runs_as_local_development():
    settings = Settings()
    assert not settings.deployed
    assert settings.show_api_docs


def test_reads_environment_variables_case_insensitively(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("log_level", "debug")
    monkeypatch.setenv("DATABASE_URL", DB)
    settings = Settings()
    assert settings.environment is Environment.STAGING
    assert settings.log_level == "DEBUG"
    assert settings.deployed
    assert settings.database_url == DB


def test_misspelled_environment_is_refused(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "prodution")
    with pytest.raises(ValidationError):
        Settings()


def test_unknown_log_level_is_refused(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "LOUD")
    with pytest.raises(ValidationError, match="unknown log level"):
        Settings()


def test_cloud_run_requires_an_explicit_environment(monkeypatch):
    monkeypatch.setenv("K_SERVICE", "portal-staging")
    with pytest.raises(ValidationError, match="ENVIRONMENT must be set on Cloud Run"):
        Settings()
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("DATABASE_URL", DB)
    assert Settings().environment is Environment.STAGING


def test_production_hides_api_docs():
    assert not Settings(environment="production", database_url=DB).show_api_docs
    assert Settings(environment="staging", database_url=DB).show_api_docs


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_deployed_environments_require_a_database_url(environment):
    with pytest.raises(ValidationError, match="DATABASE_URL must be set"):
        Settings(environment=environment)


def test_database_url_must_use_the_psycopg_driver():
    with pytest.raises(ValidationError, match="postgresql\\+psycopg://"):
        Settings(database_url="postgres://localhost/arqproj_dev")
