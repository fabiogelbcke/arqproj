"""Deployment settings, read from environment variables and checked at startup.

Only how this deployment runs belongs here. Anything about an office (its name,
domains, Drive connection) lives in the database, never in environment variables.
"""

from __future__ import annotations

import logging
import os
import re
from enum import StrEnum

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The app connects as a restricted role that row-level security applies to; only
# migrations (and local admin commands) use the owner role. Locally the owner is
# the developer's own PostgreSQL user.
LOCAL_DATABASE_URL = "postgresql+psycopg://arqproj_app@localhost:5432/arqproj_dev"
LOCAL_MIGRATION_DATABASE_URL = "postgresql+psycopg://localhost:5432/arqproj_dev"
LOCAL_RUNTIME_ROLE = "arqproj_app"


class Environment(StrEnum):
    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    environment: Environment = Environment.LOCAL
    log_level: str = "INFO"
    # The app's restricted login. Local default: arqproj_app on this machine.
    # Required when deployed.
    database_url: str = LOCAL_DATABASE_URL
    # The owner login, used only by migrations and local admin commands.
    migration_database_url: str = LOCAL_MIGRATION_DATABASE_URL
    # The login DATABASE_URL uses; `backend.commands.provision` makes it a member of the
    # database's app group role, which holds the privileges migrations grant.
    database_runtime_role: str = LOCAL_RUNTIME_ROLE
    # Lets Cloud Logging group a request's log lines by trace. Optional.
    google_cloud_project: str | None = None

    @field_validator("log_level")
    @classmethod
    def _known_log_level(cls, value: str) -> str:
        level = value.strip().upper()
        if level not in logging.getLevelNamesMapping():
            raise ValueError(f"unknown log level {value!r}")
        return level

    @field_validator("database_runtime_role")
    @classmethod
    def _plain_role_name(cls, value: str) -> str:
        # A plain role name (Cloud SQL IAM logins also contain '@' and '.').
        if not re.fullmatch(r"[a-z_][a-z0-9_.@-]{0,62}", value):
            raise ValueError(f"unexpected database role name {value!r}")
        return value

    @field_validator("database_url", "migration_database_url")
    @classmethod
    def _postgres_with_psycopg(cls, value: str) -> str:
        if not value.startswith("postgresql+psycopg://"):
            raise ValueError("database URLs must start with postgresql+psycopg://")
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
