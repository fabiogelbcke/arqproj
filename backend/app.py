"""Application factory for the multi-tenant backend.

Run locally:  uv run uvicorn backend.app:create_app --factory --reload
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx2
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from posthog import Posthog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.db import runtime_role
from backend.db.engine import create_engine, create_sessionmaker
from backend.settings import Settings
from backend.storage.google import GoogleDriveStorage, ServerIdentity
from backend.tenancy.middleware import TenantMiddleware
from backend.web import (
    admin,
    auth,
    drive,
    email_confirmation,
    google_signin,
    health,
    home,
    legal,
    maintenance,
    office,
    office_signup,
    onboarding,
    page_edit,
    page_files,
    page_stages,
    page_uploads,
    pages,
    painel,
    project_settings,
    projects,
    proposals,
    shares,
    subscribe,
    team,
    tenant,
    unsubscribe,
)
from backend.web.build import BuildIdMiddleware
from backend.web.errors import ApiError, handle_api_error, handle_invalid_request
from backend.web.request_id import RequestIdLogFilter, RequestIdMiddleware


class _CloudLoggingFormatter(logging.Formatter):
    """One JSON object per line, in the shape Google Cloud Logging reads:
    `severity` and `message` become the entry's level and text; with the project
    ID known, the trace field groups all lines of one request together."""

    def __init__(self, project: str | None) -> None:
        super().__init__()
        self.project = project

    def format(self, record: logging.LogRecord) -> str:
        request_id = getattr(record, "request_id", "-")
        entry = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "request_id": request_id,
        }
        if self.project and request_id != "-":
            entry["logging.googleapis.com/trace"] = f"projects/{self.project}/traces/{request_id}"
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


class _StdoutHandler(logging.StreamHandler):
    """Writes to whatever `sys.stdout` is at the moment, not the one at startup,
    so tools that swap stdout (like test output capture) never see a stale stream."""

    @property
    def stream(self):
        return sys.stdout

    @stream.setter
    def stream(self, _value) -> None:
        pass


def configure_logging(settings: Settings) -> None:
    handler = _StdoutHandler()
    handler.addFilter(RequestIdLogFilter())
    if settings.deployed:
        handler.setFormatter(_CloudLoggingFormatter(settings.google_cloud_project))
    else:
        handler.setFormatter(
            logging.Formatter("%(levelname)s %(name)s [%(request_id)s]: %(message)s")
        )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(settings.log_level)


class PostHogContextMiddleware:
    """One PostHog context per HTTP request, tagged with its office (tenant), so
    every event of the request counts for that office: as a `tenant` property and
    as PostHog's `tenant` group. The signed-in staff member is identified where
    their session is already looked up (`web.auth.current_account`), so this adds
    no query of its own. Clients and suppliers stay personless."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        posthog_client: Posthog | None = getattr(scope["app"].state, "posthog", None)
        if scope["type"] != "http" or posthog_client is None:
            await self.app(scope, receive, send)
            return
        with posthog_client.new_context(fresh=True):
            tenant = scope.get("state", {}).get("tenant")
            if tenant is not None:
                posthog_client.tag("tenant", tenant.slug)
                posthog_client.tag("$groups", {"tenant": str(tenant.id)})
            try:
                await self.app(scope, receive, send)
            except Exception as error:
                # Here, inside the request's context (its person and office), before
                # RequestIdMiddleware answers it with the support code; it carries on
                # up unchanged.
                posthog_client.capture_exception(error)
                raise


async def verify_runtime_login(engine, settings: Settings) -> None:
    """Refuse to serve unless connected as the restricted login provisioning checked.

    DATABASE_URL and DATABASE_RUNTIME_ROLE are separate settings; if they disagree
    (or the login can get around isolation) the app would run with an unchecked
    identity, so it stops at startup instead.
    """
    async with engine.connect() as connection:
        login = await connection.scalar(text("SELECT session_user"))
        if login != settings.database_runtime_role:
            raise RuntimeError(
                f"DATABASE_URL logs in as {login!r}, but DATABASE_RUNTIME_ROLE is "
                f"{settings.database_runtime_role!r}"
            )
        lifecycle_access = await connection.scalar(
            text(
                "SELECT has_table_privilege(current_user, 'tenants', 'INSERT,DELETE') "
                "OR has_column_privilege(current_user, 'tenants', 'status', 'UPDATE') "
                "OR EXISTS (SELECT 1 FROM pg_roles WHERE rolname = current_database() || "
                "'_operator' AND pg_has_role(current_user, oid, 'MEMBER'))"
            )
        )
        problems = (
            await connection.execute(text(runtime_role.PROBLEMS_SQL_SQLALCHEMY), {"login": login})
        ).all()
    if problems:
        raise RuntimeError(
            f"refusing to serve as {login!r}, which could get around tenant isolation: "
            f"{runtime_role.describe(problems)}"
        )
    if lifecycle_access:
        raise RuntimeError("app login must not have operator lifecycle privileges")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # One connection pool per process, closed on shutdown. Startup checks the login
    # once (a single query), so a misconfigured deployment fails before serving.
    settings = app.state.settings
    # Product analytics, only where configured: tests, CI and local runs send
    # nothing unless POSTHOG_PROJECT_TOKEN and POSTHOG_HOST are set on purpose.
    posthog_client: Posthog | None = None
    if settings.posthog_project_token and settings.posthog_host:
        posthog_client = Posthog(
            settings.posthog_project_token,
            host=settings.posthog_host,
            enable_exception_autocapture=True,
        )
    app.state.posthog = posthog_client

    operator_engine = None
    engine = create_engine(settings)
    try:
        await verify_runtime_login(engine, settings)
        app.state.sessionmaker = create_sessionmaker(engine)
        if settings.operator_database_url:
            operator_engine = create_async_engine(
                settings.operator_database_url, pool_size=1, max_overflow=1, pool_pre_ping=True
            )
            async with operator_engine.connect() as connection:
                login = await connection.scalar(text("SELECT session_user"))
                problems = (
                    await connection.execute(
                        text(runtime_role.PROBLEMS_SQL_SQLALCHEMY), {"login": login}
                    )
                ).all()
                permitted = await connection.scalar(
                    text(
                        "SELECT pg_has_role(current_user, "
                        "current_database() || '_operator', 'USAGE')"
                    )
                )
                if problems or not permitted or login == settings.database_runtime_role:
                    raise RuntimeError("operator database login must be separate and restricted")
            app.state.operator_sessionmaker = create_sessionmaker(operator_engine)
        # One HTTP client for Google, and the server's own Drive identity.
        app.state.http = httpx2.AsyncClient(timeout=30)
        app.state.google = GoogleDriveStorage(ServerIdentity(), app.state.http)
        yield
    finally:
        if getattr(app.state, "http", None) is not None:
            await app.state.http.aclose()
        if posthog_client is not None:
            posthog_client.shutdown()  # sends what is still queued
        if operator_engine is not None:
            await operator_engine.dispose()
        await engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    settings.require_real_app_secret()
    configure_logging(settings)
    docs = settings.show_api_docs
    app = FastAPI(
        title="Portal",
        lifespan=lifespan,
        docs_url="/api/docs" if docs else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if docs else None,
    )
    app.state.settings = settings
    app.include_router(health.router)
    app.include_router(home.router)
    app.include_router(legal.router)
    app.include_router(maintenance.router)
    app.include_router(admin.router)  # before the pages: /admin is no project's
    app.include_router(office_signup.router)  # likewise /criar-escritorio
    app.include_router(auth.router)
    app.include_router(google_signin.router)
    app.include_router(email_confirmation.router)
    app.include_router(tenant.router)
    app.include_router(drive.router)
    app.include_router(onboarding.router)
    app.include_router(office.router)
    app.include_router(team.router)
    app.include_router(projects.router)
    app.include_router(subscribe.router)
    app.include_router(shares.router)
    app.include_router(project_settings.router)
    app.include_router(proposals.router)
    app.include_router(painel.router)
    app.include_router(page_edit.router)
    app.include_router(page_files.router)
    app.include_router(page_stages.router)
    app.include_router(page_uploads.router)
    app.include_router(unsubscribe.router)
    # Last: `/{slug}` answers any single-segment address the routes above don't.
    app.include_router(pages.router)
    app.add_exception_handler(ApiError, handle_api_error)
    app.add_exception_handler(RequestValidationError, handle_invalid_request)
    # Added innermost first: request IDs wrap everything, so even a 404 for an
    # unknown host or a redirect carries an ID and logs with it. The PostHog
    # context sits inside tenant resolution, to tag the request's office.
    app.add_middleware(PostHogContextMiddleware)
    app.add_middleware(TenantMiddleware)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(BuildIdMiddleware, build_id=settings.build_id)
    return app
