"""Application factory for the multi-tenant backend.

Run locally:  uv run uvicorn backend.app:create_app --factory --reload
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.db.engine import create_engine, create_sessionmaker
from backend.settings import Settings
from backend.tenancy.middleware import OfficeMiddleware
from backend.web import health
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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # One connection pool per process, closed on shutdown. Creating the engine
    # does not connect; the first query does, so startup never waits on the database.
    engine = create_engine(app.state.settings)
    app.state.sessionmaker = create_sessionmaker(engine)
    try:
        yield
    finally:
        await engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
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
    # Added innermost first: request IDs wrap everything, so even a 404 for an
    # unknown host or a redirect carries an ID and logs with it.
    app.add_middleware(OfficeMiddleware)
    app.add_middleware(RequestIdMiddleware)
    return app
