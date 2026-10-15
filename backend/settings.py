"""Deployment settings, read from environment variables and checked at startup.

Only how this deployment runs belongs here. Anything about an office (its name,
domains, Drive connection) lives in the database, never in environment variables.
"""

from __future__ import annotations

import logging
import os
from enum import StrEnum

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LOCAL_DATABASE_URL = "postgresql+psycopg://localhost:5432/arqproj_dev"


class Environment(StrEnum):
    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    environment: Environment = Environment.LOCAL
    log_level: str = "INFO"
    # Local default: the developer's own PostgreSQL. Required when deployed.
    database_url: str = LOCAL_DATABASE_URL

    @field_validator("log_level")
    @classmethod
    def _known_log_level(cls, value: str) -> str:
        level = value.strip().upper()
        if level not in logging.getLevelNamesMapping():
            raise ValueError(f"unknown log level {value!r}")
        return level

    @field_validator("database_url")
    @classmethod
    def _postgres_with_psycopg(cls, value: str) -> str:
        if not value.startswith("postgresql+psycopg://"):
            raise ValueError("DATABASE_URL must start with postgresql+psycopg://")
        return value

    @model_validator(mode="after")
    def _explicit_environment_on_cloud_run(self) -> Settings:
        # Cloud Run sets K_SERVICE. A deployed service must say what it is: a
        # forgotten ENVIRONMENT would otherwise silently run with local defaults.
        if os.environ.get("K_SERVICE") and "environment" not in self.model_fields_set:
            raise ValueError("ENVIRONMENT must be set on Cloud Run (staging or production)")
        return self

    @model_validator(mode="after")
    def _explicit_database_when_deployed(self) -> Settings:
        if self.deployed and "database_url" not in self.model_fields_set:
            raise ValueError("DATABASE_URL must be set in staging and production")
        return self

    @property
    def deployed(self) -> bool:
        return self.environment in (Environment.STAGING, Environment.PRODUCTION)

    @property
    def show_api_docs(self) -> bool:
        """Interactive API docs help development; production does not publish them."""
        return self.environment is not Environment.PRODUCTION
