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
from backend.web import health


class _CloudLoggingFormatter(logging.Formatter):
    """One JSON object per line, in the shape Google Cloud Logging reads:
    `severity` and `message` become the entry's level and text."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def configure_logging(settings: Settings) -> None:
    handler = logging.StreamHandler(sys.stdout)
    if settings.deployed:
        handler.setFormatter(_CloudLoggingFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
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
    return app
