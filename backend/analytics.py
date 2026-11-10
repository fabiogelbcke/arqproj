"""Product analytics (A39): sending events to PostHog from a request.

Staff events go through the request's PostHog context (`app.PostHogContextMiddleware`),
which already carries the office and, once `web.auth` has looked up the session, the
signed-in person. Visitor events (clients, suppliers, anyone with a share link) are
personless: they carry an anonymous id that changes every day, so distinct visitors
can be counted but no one can be followed from one day to the next, and nothing is
stored. Without PostHog configured (everywhere but production) nothing is sent.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import UTC, datetime
from enum import StrEnum

from fastapi import Request

from backend.security.keys import keyed_hash
from backend.web.attempts import device as address

log = logging.getLogger(__name__)

_TABLET = re.compile(r"iPad|Tablet", re.I)
_PHONE = re.compile(r"iPhone|Android.+Mobile|Windows Phone", re.I)


class AnalyticsEvent(StrEnum):
    """Every event the server sends (A39). The values are PostHog's event names:
    its dashboards and insights find events by them, so a value never changes."""

    # Signing in and the account.
    USER_SIGNED_IN = "user_signed_in"
    USER_SIGNED_OUT = "user_signed_out"
    PASSWORD_SET = "password_set"
    PAGE_TOUR_SEEN = "page_tour_seen"
    # The office.
    OFFICE_SETTINGS_CHANGED = "office_settings_changed"
    OFFICE_LOGO_SET = "office_logo_set"
    OFFICE_LOGO_REMOVED = "office_logo_removed"
    DRIVE_CONNECTED = "drive_connected"
    DRIVE_DISCONNECTED = "drive_disconnected"
    # Projects and their pages.
    PROJECT_CREATED = "project_created"
    PROJECT_CONTENT_UPDATED = "project_content_updated"
    PROJECT_PUBLISHED = "project_published"
    PROJECT_COVER_SET = "project_cover_set"
    PROJECT_COVER_REMOVED = "project_cover_removed"
    PROJECT_COMPLETED = "project_completed"
    MEETING_SCHEDULED = "meeting_scheduled"
    MEETING_CLEARED = "meeting_cleared"
    STAGE_ADDED = "stage_added"
    STAGE_COMPLETION_CHANGED = "stage_completion_changed"
    STAGE_RENAMED = "stage_renamed"
    STAGE_MOVED = "stage_moved"
    STAGES_REORDERED = "stages_reordered"
    STAGE_REMOVED = "stage_removed"
    SECTION_CREATED = "section_created"
    UPLOAD_STARTED = "upload_started"
    UPLOAD_FAILED = "upload_failed"
    FILE_HIDDEN = "file_hidden"
    FILE_MOVED = "file_moved"
    COMPARISON_UPLOAD_STARTED = "comparison_upload_started"
    COMPARISON_EDITED = "comparison_edited"
    COMPARISON_HIDDEN = "comparison_hidden"
    COMPARISON_MOVED = "comparison_moved"
    # Share links: staff's, or a visitor's when a client makes one.
    SHARE_LINK_CREATED = "share_link_created"
    SHARE_LINK_RENEWED = "share_link_renewed"
    SHARE_LINK_DISABLED = "share_link_disabled"
    # The portfolio (A45).
    PORTFOLIO_PUBLISHED = "portfolio_published"
    PORTFOLIO_UNPUBLISHED = "portfolio_unpublished"
    PORTFOLIO_FORMAT_CHANGED = "portfolio_format_changed"
    PORTFOLIO_ENTRY_ADDED = "portfolio_entry_added"
    PORTFOLIO_ENTRY_REMOVED = "portfolio_entry_removed"
    PORTFOLIO_ENTRIES_MERGED = "portfolio_entries_merged"
    PORTFOLIO_ENTRY_SPLIT = "portfolio_entry_split"
    PORTFOLIO_SECTION_ADDED = "portfolio_section_added"
    PORTFOLIO_SECTION_REMOVED = "portfolio_section_removed"
    PORTFOLIO_PHOTO_ADDED = "portfolio_photo_added"
    PORTFOLIO_COMPARISON_SET = "portfolio_comparison_set"
    PORTFOLIO_COMPARISON_REMOVED = "portfolio_comparison_removed"
    PORTFOLIO_VIDEO_ADDED = "portfolio_video_added"
    PORTFOLIO_VIDEO_UPLOAD_FAILED = "portfolio_video_upload_failed"
    # Clients and other visitors: personless.
    PAGE_UNLOCK_TRIED = "page_unlock_tried"
    MEETING_ADDED_TO_CALENDAR = "meeting_added_to_calendar"
    SHARE_PAGE_VIEWED = "share_page_viewed"
    SHARE_UNLOCK_TRIED = "share_unlock_tried"
    CLIENT_EMAIL_SUBSCRIBED = "client_email_subscribed"
    CLIENT_EMAIL_UNSUBSCRIBED = "client_email_unsubscribed"
    # Personless counts: bytes sent, update emails per office.
    FILE_TRANSFER = "file_transfer"
    UPDATE_EMAILS_SENT = "update_emails_sent"


class SignInMethod(StrEnum):
    """How a staff member signed in (`user_signed_in`'s `method`)."""

    PASSWORD = "password"
    GOOGLE = "google"
    LINK = "link"  # a password chosen from an email's link
    JOIN = "join"  # joined through the office's shared link


def capture(request: Request, event: AnalyticsEvent, properties: dict | None = None) -> None:
    """A staff action, as this request's person and office."""
    client = getattr(request.app.state, "posthog", None)
    if client is not None:
        client.capture(event, properties=properties or {})


def device_kind(user_agent: str) -> str:
    """ "phone", "tablet" or "computer", from the browser's User-Agent."""
    if _TABLET.search(user_agent):
        return "tablet"
    if _PHONE.search(user_agent):
        return "phone"
    return "tablet" if "Android" in user_agent else "computer"  # Android without "Mobile"


def visitor_id(request: Request, today: datetime | None = None) -> str:
    """An anonymous id for today's visitor: a keyed hash of their address, browser
    and the date. The key comes from APP_SECRET, so it can't be recomputed outside
    the app; the date makes it change every day."""
    day = (today or datetime.now(UTC)).date().isoformat()
    seen = f"{day}|{address(request)}|{request.headers.get('user-agent', '')}"
    return keyed_hash(request.app.state.settings.app_secret, "analytics-visitor", seen)[:20]


def visitor_properties(request: Request, tenant_id: uuid.UUID) -> dict:
    """What every visitor event carries: personless, the office, the device."""
    tenant = getattr(request.state, "tenant", None)
    return {
        "$process_person_profile": False,
        "$groups": {"tenant": str(tenant_id)},
        "tenant": tenant.slug if tenant is not None else None,
        "viewer": "visitor",  # as the browser's visitor events, so staff ones can be told apart
        "device": device_kind(request.headers.get("user-agent", "")),
    }


def capture_visit(
    request: Request, tenant_id: uuid.UUID, event: AnalyticsEvent, properties: dict | None = None
) -> None:
    """Something a client or other visitor did. Never fails the request."""
    client = getattr(request.app.state, "posthog", None)
    if client is None:
        return
    try:
        client.capture(
            event,
            distinct_id=f"visitor:{visitor_id(request)}",
            properties=visitor_properties(request, tenant_id) | (properties or {}),
        )
    except Exception:
        log.exception("analytics: %s failed for tenant %s", event, tenant_id)
