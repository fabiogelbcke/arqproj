"""The longest text staff can enter in each field: the limits the server enforces.

`make api-types` writes them to `frontend/src/api/limits.json`, which the screens'
inputs (maxLength) and the preview page read. So a limit changes here, in the
constant the server checks, and the screens follow; a test fails if the committed
file no longer matches. Some limits are for names entered from now on: the
database allows more, and a name saved before the limit stays as it is.
"""

from __future__ import annotations

from backend.identity.emails import EMAIL_LIMIT
from backend.projects.creation import CLIENT_NAME_LIMIT, SLUG_MAX
from backend.projects.creation import NAME_MAX as PROJECT_NAME_MAX
from backend.projects.models import MEETING_LOCATION_MAX, MEETING_TITLE_MAX
from backend.web.office import NAME_LIMIT as OFFICE_NAME_LIMIT
from backend.web.page_edit import DESCRIPTION_MAX, DETAIL_TEXT_MAX, NOTES_MAX
from backend.web.page_stages import STAGE_TITLE_MAX
from backend.web.project_settings import PAGE_PASSWORD_MAX
from backend.web.team import NAME_MAX as STAFF_NAME_MAX

FIELD_LIMITS: dict[str, int] = {
    "projectName": PROJECT_NAME_MAX,
    "clientName": CLIENT_NAME_LIMIT,
    "slug": SLUG_MAX,
    "description": DESCRIPTION_MAX,
    "stageTitle": STAGE_TITLE_MAX,
    "stageNotes": NOTES_MAX,
    "detailText": DETAIL_TEXT_MAX,
    "meetingTitle": MEETING_TITLE_MAX,
    "meetingLocation": MEETING_LOCATION_MAX,
    "officeName": OFFICE_NAME_LIMIT,
    "staffName": STAFF_NAME_MAX,
    "email": EMAIL_LIMIT,
    "pagePassword": PAGE_PASSWORD_MAX,
}
