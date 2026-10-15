import pytest
from pydantic import ValidationError

from backend.settings import Environment, Settings


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    """Each test starts without the variables these settings read."""
    for name in ("ENVIRONMENT", "LOG_LEVEL", "K_SERVICE"):
        monkeypatch.delenv(name, raising=False)


def test_defaults_are_for_local_development():
    settings = Settings()
    assert settings.environment is Environment.LOCAL
    assert settings.log_level == "INFO"
    assert not settings.deployed
    assert settings.show_api_docs


def test_reads_environment_variables_case_insensitively(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("log_level", "debug")
    settings = Settings()
    assert settings.environment is Environment.STAGING
    assert settings.log_level == "DEBUG"
    assert settings.deployed


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
    assert Settings().environment is Environment.STAGING


def test_production_hides_api_docs():
    assert not Settings(environment="production").show_api_docs
    assert Settings(environment="staging").show_api_docs
