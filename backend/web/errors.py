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
    OPERATOR_ACTION_CONFLICT = "operator_action_conflict"
    OPERATOR_ACTION_FAILED = "operator_action_failed"
    OPERATOR_ACTIONS_UNAVAILABLE = "operator_actions_unavailable"
    SIGNUP_LINK_INVALID = "signup_link_invalid"  # an office signup link used, expired or unknown
    OFFICE_ADDRESS_TAKEN = "office_address_taken"  # another office has that address
    INVALID_OFFICE_ADDRESS = "invalid_office_address"  # not a usable subdomain, or reserved
    NOT_SIGNED_IN = "not_signed_in"
    CSRF_TOKEN_MISSING_OR_WRONG = "csrf_token_missing_or_wrong"
    INVALID_CREDENTIALS = "invalid_credentials"
    INVALID_REQUEST = "invalid_request"  # malformed body or missing fields: a bug, not the user
    LINK_INVALID = "link_invalid"  # unknown, used, expired, replaced or another office's
    PASSWORD_TOO_SHORT = "password_too_short"
    OWNER_ONLY = "owner_only"  # only the office's owners may do this
    DRIVE_NOT_CONFIGURED = "drive_not_configured"  # this deployment has no Google app set up
    SIGNIN_NOT_CONFIGURED = "signin_not_configured"  # no Google app for signing in here
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
    UNKNOWN_PROJECT_TYPE = "unknown_project_type"
    UNKNOWN_STAGE = "unknown_stage"  # not a built-in stage, or chosen twice
    UNKNOWN_MEMBER = "unknown_member"  # not one of the office's staff (A41)
    FEATURE_OFF = "feature_off"  # not switched on for this office (A40)
    INVALID_SLUG = "invalid_slug"  # letters, numbers and hyphens; some words are the app's
    PROJECT_NAME_TAKEN = "project_name_taken"  # `conflict_name` as typed by the office
    SLUG_TAKEN = "slug_taken"  # `conflict_name` names the project that has it, when known
    PROJECT_NOT_FOUND = "project_not_found"  # unknown, deleted or another office's
    PROJECT_CHANGED = "project_changed"  # someone else saved it meanwhile: reload
    INVALID_STATUS_CHANGE = "invalid_status_change"
    PROJECT_HAS_NO_FOLDER = "project_has_no_folder"
    PROJECT_ARCHIVED = "project_archived"  # viewable, not changed (plan section 22)
    COVER_WRONG_TYPE = "cover_wrong_type"
    COVER_TOO_LARGE = "cover_too_large"
    PAGE_NOT_FOUND = "page_not_found"  # unknown address, draft or deleted: never told apart
    PAGE_LOCKED = "page_locked"  # protected by a password
    PAGE_UNAVAILABLE = "page_unavailable"  # Drive disconnected: back once reconnected
    WRONG_PAGE_PASSWORD = "wrong_page_password"
    TOO_MANY_ATTEMPTS = "too_many_attempts"  # wait 15 minutes
    RECIPIENTS_FULL = "recipients_full"  # the project has as many addresses as it may (20)
    PASSWORD_REQUIRED = "password_required"  # password access needs a password
    INVALID_DETAIL = "invalid_detail"  # unknown, repeated, or a value of the wrong kind
    INVALID_STAGE = "invalid_stage"  # unknown, already there, blank, or nowhere to move
    INVALID_MEETING = "invalid_meeting"  # title 1-40, ends after it starts, web link
    FILES_UNAVAILABLE = "files_unavailable"  # Drive down or throttled: try again
    FILE_NOT_FOUND = "file_not_found"  # moved, deleted, or its link expired: reload
    FILE_TOO_LARGE = "file_too_large"  # over the upload limit (A31)
    VERSION_TYPE_MISMATCH = "version_type_mismatch"  # a new version of another type (A25)
    INVALID_FILE_NAME = "invalid_file_name"  # blank after cleaning
    HIDDEN_FILE_NAME = "hidden_file_name"  # starts with "_": the page never shows it
    STAGE_HAS_NO_FOLDER = "stage_has_no_folder"  # nowhere in Drive to put the file
    INVALID_FOLDER_NAME = "invalid_folder_name"  # a section's: blank, or starts with "_"
    FOLDER_EXISTS = "folder_exists"  # the stage already has a section of that name
    FOLDER_NOT_FOUND = "folder_not_found"  # the section is gone from Drive: reload
    FOLDER_NOT_OURS = "folder_not_ours"  # a section made straight in Drive: change it there
    UPLOAD_FAILED = "upload_failed"  # the browser couldn't finish sending: logged, with the code
    FILE_NOT_OURS = "file_not_ours"  # put straight into Drive: rename it there (drive.file)
    FILE_NOT_OURS_TO_MOVE = "file_not_ours_to_move"  # put straight into Drive: move it there
    INVALID_STAFF_NAME = "invalid_staff_name"  # blank, or over 80 characters
    ALREADY_STAFF = "already_staff"  # `conflict_name`: the account with that email
    NOT_AN_INVITE = "not_an_invite"  # unknown, or already in (only pending invites)
    JOIN_LINK_INVALID = "join_link_invalid"  # turned off, replaced, or another office's
    ACCOUNT_EXISTS = "account_exists"  # joining or correcting to an address with an account
    EMAIL_UNCONFIRMED = "email_unconfirmed"  # joined by the shared link: confirm the email first
    EMAIL_CODE_WRONG = "email_code_wrong"  # another try is left
    EMAIL_CODE_EXPIRED = "email_code_expired"  # expired, or too many wrong: ask for a new one
    EMAIL_CODE_RECENT = "email_code_recent"  # one went in the last 2 minutes: wait
    EMAIL_NOT_SENT = "email_not_sent"  # the email couldn't go: logged; try again
    ALREADY_CONFIRMED = "already_confirmed"  # nothing to confirm or correct: reload
    # A share link (A37): unknown, turned off, expired, or its project gone: never told apart.
    SHARE_NOT_FOUND = "share_not_found"
    SHARE_TOO_LARGE = "share_too_large"  # over 300 MB of files
    SHARE_FILES_CHANGED = "share_files_changed"  # a file picked left the page meanwhile: reload
    SHARE_DAILY_LIMIT = "share_daily_limit"  # the link served its day's downloads
    SHARE_LOCKED = "share_locked"  # the link has a password, not typed on this device
    WRONG_SHARE_PASSWORD = "wrong_share_password"
    PROPOSAL_NOT_FOUND = "proposal_not_found"  # no such version, or none saved yet


class ErrorOut(BaseModel):
    error: ErrorCode
    # Office content the screen can show with the error, e.g. who has an address.
    conflict_name: str | None = None


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: ErrorCode,
        conflict_name: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(code.value)
        self.status_code = status_code
        self.code = code
        self.conflict_name = conflict_name
        self.headers = headers or {}


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
    return JSONResponse(body, status_code=error.status_code, headers=error.headers)
