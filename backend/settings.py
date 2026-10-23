"""Deployment settings, read from environment variables and checked at startup.

Only how this deployment runs belongs here. Anything about a tenant (its name,
domains, Drive connection) lives in the database, never in environment variables.
"""

from __future__ import annotations

import logging
import os
import re
from enum import StrEnum
from pathlib import Path

from pydantic import Field, field_validator, model_validator
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
    # Identifies the release; sent as X-Build-Id so open staff-app tabs notice a
    # new deploy. The image build sets it (step 1.7); "dev" locally.
    build_id: str = "dev"
    # Derives the keys for signing short-lived notes and encrypting stored tokens
    # (backend.security.keys). Required, at least 32 characters, when deployed.
    app_secret: str = "local-development-secret-never-used-when-deployed"
    # Google proxies in front of the app, each appending the address it saw to
    # X-Forwarded-For: 1 with Cloud Run alone, 2 behind the external load balancer
    # (A21). The visitor's own address is that many entries from the end; anything
    # before it the visitor may have written themselves.
    forwarded_hops: int = Field(default=1, ge=1, le=3)
    # Google sign-in for connecting an office's Drive (the app registration).
    google_oauth_client_id: str | None = None
    google_oauth_client_secret: str | None = None
    # The shared return address registered with Google; it forwards to the office
    # that started the connection (backend/web/drive.py).
    google_oauth_redirect_uri: str = "http://127.0.0.1:5173/api/drive/callback"
    # The Google identity office folders are shared with for reading.
    drive_reader_identity: str | None = None
    # Local development: offices whose storage kind is "folder" read files under
    # this folder (the fictional dataset; README "Local-folder test data").
    local_storage_root: str = str(
        Path(__file__).resolve().parent.parent / "local-test-data" / "Projects"
    )
    # The staff app's build (`npm run build` in frontend/).
    frontend_dist: str = str(Path(__file__).resolve().parent.parent / "frontend" / "dist")
    # Client email updates (A32, plan section 14). With a Resend key, emails go
    # through Resend; without one they are written to `email_outbox` to open by hand.
    resend_api_key: str | None = None
    email_outbox: str = str(Path(__file__).resolve().parent.parent / "local-test-data" / "outbox")
    # The product's general sender domain, once verified with Resend; until then
    # Resend's test sender, which delivers only to the Resend account's own address.
    email_domain: str | None = None
    # Offices that send from their own verified domain, as JSON: {"alinea": "alineaarquitetos.com"}.
    email_office_domains: dict[str, str] = {}
    # Where links in locally written emails point: `make dev`'s port (`make serve`
    # sets 8000).
    local_site_port: int = 5173
    # The scheduler's call to /internal/maintenance (A09, A19): the service's own
    # URL as the token's audience, and the scheduler's service account. Unset
    # (locally), that address doesn't exist; run backend.commands.maintenance.
    maintenance_audience: str | None = None
    maintenance_caller: str | None = None
    # Optional product analytics. Production remains a no-op until both are configured.
    posthog_api_key: str | None = None
    posthog_host: str | None = None

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

    def require_real_app_secret(self) -> None:
        """The web app signs and encrypts with APP_SECRET, so a deployed app refuses
        to start without a real one. Checked at app start, not whenever settings
        load: migrations and admin commands never use it."""
        if self.deployed and (
            "app_secret" not in self.model_fields_set or len(self.app_secret) < 32
        ):
            raise ValueError("APP_SECRET (32+ characters) must be set in staging and production")

    @property
    def posthog_configured(self) -> bool:
        return bool(self.posthog_api_key and self.posthog_host)

    @property
    def drive_configured(self) -> bool:
        return bool(
            self.google_oauth_client_id
            and self.google_oauth_client_secret
            and self.drive_reader_identity
        )

    @property
    def deployed(self) -> bool:
        return self.environment in (Environment.STAGING, Environment.PRODUCTION)

    @property
    def email_staff_only(self) -> bool:
        """Outside production, emails go only to the office's own staff accounts, so
        a test can never reach a client (section 14). Not a setting: nothing can
        switch it off by mistake."""
        return self.environment is not Environment.PRODUCTION

    @property
    def show_api_docs(self) -> bool:
        """Interactive API docs help development; production does not publish them."""
        return self.environment is not Environment.PRODUCTION
