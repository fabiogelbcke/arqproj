"""Application factory for the multi-tenant backend.

Run locally:  uv run uvicorn backend.app:create_app --factory --reload
"""

from __future__ import annotations

import atexit
import json
import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http.cookies import CookieError, SimpleCookie

import httpx2
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from posthog import Posthog
from sqlalchemy import text
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from backend.db import runtime_role
from backend.db.engine import create_engine, create_sessionmaker
from backend.db.isolation import scope_to_tenant
from backend.identity import sessions
from backend.settings import Settings
from backend.storage.google import GoogleDriveStorage, ServerIdentity
from backend.tenancy.middleware import TenantMiddleware
from backend.web import (
    auth,
    drive,
    health,
    home,
    legal,
    maintenance,
    office,
    onboarding,
    page_edit,
    page_files,
    page_stages,
    page_uploads,
    pages,
    painel,
    project_settings,
    projects,
    subscribe,
    team,
    tenant,
    unsubscribe,
)
from backend.web.build import BuildIdMiddleware
from backend.web.errors import ApiError, handle_api_error, handle_invalid_request
from backend.web.request_id import RequestIdLogFilter, RequestIdMiddleware


class PosthogRequestContextMiddleware:
    """Bind the authenticated staff UUID to one fresh PostHog request context."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        state = scope["app"].state
        posthog = getattr(state, "posthog", None)
        tenant = scope.get("state", {}).get("tenant")
        if posthog is None or tenant is None:
            await self.app(scope, receive, send)
            return

        with posthog.new_context(fresh=True):
            try:
                user_id = await self._authenticated_user_id(scope)
                if user_id is not None:
                    posthog.identify_context(user_id)
                await self.app(scope, receive, send)
            except Exception as error:
                posthog.capture_exception(error)
                raise

    async def _authenticated_user_id(self, scope: Scope) -> str | None:
        try:
            cookies = SimpleCookie(Headers(scope=scope).get("cookie", ""))
        except CookieError:
            return None
        session_cookie = cookies.get("portal_session")
        if session_cookie is None:
            return None

        tenant = scope["state"]["tenant"]
        async with scope["app"].state.sessionmaker() as db:
            scope_to_tenant(db.sync_session, tenant.id)
            found = await sessions.find_active(db, session_cookie.value)
        return str(found[1].id) if found is not None else None


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


def configure_posthog_log_export(settings: Settings):
    """Export only records written to the dedicated PostHog logger."""
    from opentelemetry._logs import set_logger_provider
    from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

    logger_provider = LoggerProvider()
    set_logger_provider(logger_provider)
    exporter = OTLPLogExporter(
        endpoint=f"{settings.posthog_host.rstrip('/')}/i/v1/logs",
        headers={"Authorization": f"Bearer {settings.posthog_api_key}"},
    )
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(exporter))

    logger = logging.getLogger("backend.posthog.logs")
    logger.setLevel(logging.INFO)
    logger.addHandler(LoggingHandler(logger_provider=logger_provider))
    logger.info("PostHog log export configured")
    return logger_provider


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
        problems = (
            await connection.execute(text(runtime_role.PROBLEMS_SQL_SQLALCHEMY), {"login": login})
        ).all()
    if problems:
        raise RuntimeError(
            f"refusing to serve as {login!r}, which could get around tenant isolation: "
            f"{runtime_role.describe(problems)}"
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # One connection pool per process, closed on shutdown. Startup checks the login
    # once (a single query), so a misconfigured deployment fails before serving.
    engine = create_engine(app.state.settings)
    try:
        await verify_runtime_login(engine, app.state.settings)
        app.state.sessionmaker = create_sessionmaker(engine)
        if app.state.settings.posthog_configured:
            app.state.posthog = Posthog(
                app.state.settings.posthog_api_key,
                host=app.state.settings.posthog_host,
                enable_exception_autocapture=True,
            )
            atexit.register(app.state.posthog.shutdown)
            app.state.posthog_log_provider = configure_posthog_log_export(app.state.settings)
            logging.getLogger("backend.posthog.logs").info("backend startup completed")
        elif not app.state.settings.deployed:
            for variable in ("POSTHOG_API_KEY", "POSTHOG_HOST"):
                if not getattr(app.state.settings, variable.lower()):
                    logging.getLogger(__name__).error(
                        "%s variable required by PostHog is missing or un-configured, "
                        "this causes events to be silently missed. This error stops "
                        "appearing once %s is configured",
                        variable,
                        variable,
                    )
        # One HTTP client for Google, and the server's own Drive identity.
        app.state.http = httpx2.AsyncClient(timeout=30)
        app.state.google = GoogleDriveStorage(ServerIdentity(), app.state.http)
        yield
    finally:
        if getattr(app.state, "posthog_log_provider", None) is not None:
            logging.getLogger("backend.posthog.logs").info("backend shutdown started")
            app.state.posthog_log_provider.force_flush()
            app.state.posthog_log_provider.shutdown()
        if getattr(app.state, "posthog", None) is not None:
            app.state.posthog.flush()
        if getattr(app.state, "http", None) is not None:
            await app.state.http.aclose()
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
    app.state.posthog = None
    app.state.posthog_log_provider = None
    app.include_router(health.router)
    app.include_router(home.router)
    app.include_router(legal.router)
    app.include_router(maintenance.router)
    app.include_router(auth.router)
    app.include_router(tenant.router)
    app.include_router(drive.router)
    app.include_router(onboarding.router)
    app.include_router(office.router)
    app.include_router(team.router)
    app.include_router(projects.router)
    app.include_router(subscribe.router)
    app.include_router(project_settings.router)
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
    # Added innermost first: the PostHog context runs after tenant resolution,
    # then request IDs wrap everything, including unknown-host responses.
    app.add_middleware(PosthogRequestContextMiddleware)
    app.add_middleware(TenantMiddleware)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(BuildIdMiddleware, build_id=settings.build_id)
    return app
