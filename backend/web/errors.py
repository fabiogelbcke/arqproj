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
    DRIVE_UNREADABLE = "drive_unreadable"  # the portal cannot read the office's folder
    INVALID_OFFICE_NAME = "invalid_office_name"
    INVALID_EMAIL = "invalid_email"
    LOGO_WRONG_TYPE = "logo_wrong_type"
    LOGO_TOO_LARGE = "logo_too_large"
    INVALID_PROJECT_NAME = "invalid_project_name"
    INVALID_CLIENT_NAME = "invalid_client_name"
    UNKNOWN_TEMPLATE = "unknown_template"
    INVALID_SLUG = "invalid_slug"  # letters, numbers and hyphens; some words are the app's
    PROJECT_NAME_TAKEN = "project_name_taken"  # `conflict_name` as typed by the office
    SLUG_TAKEN = "slug_taken"
    PROJECT_NOT_FOUND = "project_not_found"  # unknown, deleted or another office's
    PROJECT_CHANGED = "project_changed"  # someone else saved it meanwhile: reload
    INVALID_STATUS_CHANGE = "invalid_status_change"
    PROJECT_HAS_NO_FOLDER = "project_has_no_folder"
    COVER_WRONG_TYPE = "cover_wrong_type"
    COVER_TOO_LARGE = "cover_too_large"  # `conflict_name` names the project that has it, when known


class ErrorOut(BaseModel):
    error: ErrorCode
    # Office content the screen can show with the error, e.g. who has an address.
    conflict_name: str | None = None


class ApiError(Exception):
    def __init__(self, status_code: int, code: ErrorCode, conflict_name: str | None = None) -> None:
        super().__init__(code.value)
        self.status_code = status_code
        self.code = code
        self.conflict_name = conflict_name


def documented(*status_codes: int) -> dict:
    """For a route's `responses=`: these statuses return an `ErrorOut`."""
    return {status: {"model": ErrorOut} for status in status_codes}


log = logging.getLogger(__name__)


async def handle_invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
    # The details (which field, why) are for us, in the log; never in the response.
    log.warning("invalid request to %s: %s", request.url.path, error.errors())
    return JSONResponse({"error": ErrorCode.INVALID_REQUEST.value}, status_code=422)


async def handle_api_error(_request: Request, error: ApiError) -> JSONResponse:
    body = {"error": error.code.value}
    if error.conflict_name is not None:
        body["conflict_name"] = error.conflict_name
    return JSONResponse(body, status_code=error.status_code)
