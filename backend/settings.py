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


class Environment(StrEnum):
    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    environment: Environment = Environment.LOCAL
    log_level: str = "INFO"

    @field_validator("log_level")
    @classmethod
    def _known_log_level(cls, value: str) -> str:
        level = value.strip().upper()
        if level not in logging.getLevelNamesMapping():
            raise ValueError(f"unknown log level {value!r}")
        return level

    @model_validator(mode="after")
    def _explicit_environment_on_cloud_run(self) -> Settings:
        # Cloud Run sets K_SERVICE. A deployed service must say what it is: a
        # forgotten ENVIRONMENT would otherwise silently run with local defaults.
        if os.environ.get("K_SERVICE") and "environment" not in self.model_fields_set:
            raise ValueError("ENVIRONMENT must be set on Cloud Run (staging or production)")
        return self

    @property
    def deployed(self) -> bool:
        return self.environment in (Environment.STAGING, Environment.PRODUCTION)

    @property
    def show_api_docs(self) -> bool:
        """Interactive API docs help development; production does not publish them."""
        return self.environment is not Environment.PRODUCTION
