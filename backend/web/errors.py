"""API errors: a status and a stable code, never text for people.

The staff screens translate each code into the office's language (AGENTS.md,
"User-facing errors"). `ErrorCode` appears in the OpenAPI schema, so the screens'
generated types list every code they must handle.
"""

from __future__ import annotations

from enum import StrEnum

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class ErrorCode(StrEnum):
    NOT_SIGNED_IN = "not_signed_in"
    CSRF_TOKEN_MISSING_OR_WRONG = "csrf_token_missing_or_wrong"
    INVALID_CREDENTIALS = "invalid_credentials"


class ErrorOut(BaseModel):
    error: ErrorCode


class ApiError(Exception):
    def __init__(self, status_code: int, code: ErrorCode) -> None:
        super().__init__(code.value)
        self.status_code = status_code
        self.code = code


def documented(*status_codes: int) -> dict:
    """For a route's `responses=`: these statuses return an `ErrorOut`."""
    return {status: {"model": ErrorOut} for status in status_codes}


async def handle_api_error(_request: Request, error: ApiError) -> JSONResponse:
    return JSONResponse({"error": error.code.value}, status_code=error.status_code)
