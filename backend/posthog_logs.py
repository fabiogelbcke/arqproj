"""Dedicated PostHog OTLP log export for purpose-written portal log lines."""

from __future__ import annotations

import logging

from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

log = logging.getLogger("backend.posthog_logs")
_HANDLER_MARKER = "_posthog_logs_exporter"


def configure_posthog_log_export(project_token: str, host: str) -> LoggerProvider:
    """Export only records emitted through this module's dedicated logger."""
    logger_provider = LoggerProvider()
    exporter = OTLPLogExporter(
        endpoint=f"{host.rstrip('/')}/i/v1/logs",
        headers={"Authorization": f"Bearer {project_token}"},
    )
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(exporter))

    # An app factory may be created more than once in one process. Replace only
    # the handler owned by this integration; all other handlers stay untouched.
    for handler in list(log.handlers):
        if getattr(handler, _HANDLER_MARKER, False):
            log.removeHandler(handler)
            handler.close()

    handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
    setattr(handler, _HANDLER_MARKER, True)
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    log.propagate = False
    return logger_provider


def shutdown_posthog_log_export(logger_provider: LoggerProvider) -> None:
    """Deliver queued dedicated records before the FastAPI process exits."""
    logger_provider.force_flush()
    logger_provider.shutdown()
