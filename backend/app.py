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
from http.cookies import SimpleCookie

import httpx2
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from posthog import Posthog
from sqlalchemy import text

from backend.db import runtime_role
from backend.db.engine import create_engine, create_sessionmaker
from backend.db.isolation import scope_to_tenant
from backend.identity import sessions
from backend.posthog_logs import (
    configure_posthog_log_export,
    shutdown_posthog_log_export,
)
from backend.posthog_logs import (
    log as posthog_log,
)
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
    onboarding,
    page_edit,
    page_files,
    page_stages,
    page_uploads,
    pages,
    painel,
    project_settings,
    projects,
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


async def capture_unhandled_exception(request: Request, error: Exception) -> None:
    """Send unhandled request exceptions to PostHog without changing their response."""
    posthog_client: Posthog | None = getattr(request.app.state, "posthog", None)
    if posthog_client is not None:
        posthog_client.capture_exception(error)
    raise error


class PostHogIdentityMiddleware:
    """Bind an authenticated account to one PostHog context per HTTP request."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        posthog_client: Posthog | None = getattr(scope["app"].state, "posthog", None)
        if posthog_client is None:
            await self.app(scope, receive, send)
            return

        with posthog_client.new_context(fresh=True):
            tenant = scope.get("state", {}).get("tenant")
            token = self._session_token(scope)
            if tenant is not None and token:
                async with scope["app"].state.sessionmaker() as db:
                    scope_to_tenant(db.sync_session, tenant.id)
                    found = await sessions.find_active(db, token)
                    if found is not None:
                        session, user = found
                        posthog_client.identify_context(str(user.id))
                        posthog_client.set_context_session(str(session.id))
            await self.app(scope, receive, send)

    @staticmethod
    def _session_token(scope) -> str | None:
        cookies = SimpleCookie()
        cookies.load(dict(scope.get("headers", [])).get(b"cookie", b"").decode("latin-1"))
        session = cookies.get(auth.COOKIE)
        return session.value if session is not None else None


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
    settings = app.state.settings
    posthog_client: Posthog | None = None
    posthog_log_provider = None
    if settings.posthog_project_token and settings.posthog_host:
        posthog_client = Posthog(
            settings.posthog_project_token,
            host=settings.posthog_host,
            enable_exception_autocapture=True,
        )
        atexit.register(posthog_client.shutdown)
        posthog_log_provider = configure_posthog_log_export(
            settings.posthog_project_token, settings.posthog_host
        )
        posthog_log.info("posthog log export initialized")
    elif not settings.deployed:
        missing = "POSTHOG_PROJECT_TOKEN" if not settings.posthog_project_token else "POSTHOG_HOST"
        raise ValueError(
            f"{missing} variable required by PostHog is missing or un-configured, "
            "this causes events to be silently missed. This error stops appearing once "
            f"{missing} is configured"
        )
    app.state.posthog = posthog_client

    engine = create_engine(settings)
    try:
        await verify_runtime_login(engine, settings)
        app.state.sessionmaker = create_sessionmaker(engine)
        # One HTTP client for Google, and the server's own Drive identity.
        app.state.http = httpx2.AsyncClient(timeout=30)
        app.state.google = GoogleDriveStorage(ServerIdentity(), app.state.http)
        yield
    finally:
        if getattr(app.state, "http", None) is not None:
            await app.state.http.aclose()
        if posthog_client is not None:
            posthog_client.flush()
        if posthog_log_provider is not None:
            posthog_log.info("posthog log export shutting down")
            shutdown_posthog_log_export(posthog_log_provider)
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
    app.add_exception_handler(Exception, capture_unhandled_exception)
    # Added innermost first: request IDs wrap everything, so even a 404 for an
    # unknown host or a redirect carries an ID and logs with it. Tenant resolution
    # must run before the PostHog context reads a tenant-scoped login session.
    app.add_middleware(PostHogIdentityMiddleware)
    app.add_middleware(TenantMiddleware)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(BuildIdMiddleware, build_id=settings.build_id)
    return app
