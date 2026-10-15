"""API errors: a status and a stable code, never text for people.

The staff screens translate each code into the office's language (AGENTS.md,
"User-facing errors"). `ErrorCode` appears in the OpenAPI schema, so the screens'
generated types list every code they must handle.
"""

from __future__ import annotations

import logging
from enum import StrEnum

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class ErrorCode(StrEnum):
    NOT_SIGNED_IN = "not_signed_in"
    CSRF_TOKEN_MISSING_OR_WRONG = "csrf_token_missing_or_wrong"
    INVALID_CREDENTIALS = "invalid_credentials"
    INVALID_REQUEST = "invalid_request"  # malformed body or missing fields: a bug, not the user
    LINK_INVALID = "link_invalid"  # unknown, used, expired, replaced or another office's
    PASSWORD_TOO_SHORT = "password_too_short"
    OWNER_ONLY = "owner_only"  # only the office's owners may do this
    DRIVE_NOT_CONFIGURED = "drive_not_configured"  # this deployment has no Google app set up
    DRIVE_DENIED = "drive_denied"  # the person cancelled at Google
    DRIVE_LINK_INVALID = "drive_link_invalid"  # expired, tampered or replayed sign-in
    DRIVE_CONNECT_FAILED = "drive_connect_failed"
    DRIVE_SHARE_FAILED = "drive_share_failed"  # the folder could not be shared with the reader
    DRIVE_OTHER_ACCOUNT = "drive_other_account"  # reconnect with the account that has the folder
    DRIVE_NOT_CONNECTED = "drive_not_connected"  # this needs the office's Drive connected first
    DRIVE_EXPIRED = "drive_expired"  # Google refused the stored grant: reconnect
    INVALID_OFFICE_NAME = "invalid_office_name"
    INVALID_EMAIL = "invalid_email"
    LOGO_WRONG_TYPE = "logo_wrong_type"
    LOGO_TOO_LARGE = "logo_too_large"


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


log = logging.getLogger(__name__)


async def handle_invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
    # The details (which field, why) are for us, in the log; never in the response.
    log.warning("invalid request to %s: %s", request.url.path, error.errors())
    return JSONResponse({"error": ErrorCode.INVALID_REQUEST.value}, status_code=422)


async def handle_api_error(_request: Request, error: ApiError) -> JSONResponse:
    return JSONResponse({"error": error.code.value}, status_code=error.status_code)
