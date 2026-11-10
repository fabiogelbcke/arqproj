"""The notice settings (A48), as the maintenance pass uses them: read once a
pass from `notice_settings`, set in "Configurações" → "Avisos"."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from backend.notifications.models import NoticeSettings, WhatsAppNews


@dataclass(frozen=True)
class Notices:
    quiet: timedelta  # a batch is due this long after its last change (A12)
    hold: timedelta  # or this long after its first
    morning: time  # the day's reminder, in the office's time zone
    evening: time  # the evening before's, for a meeting early in the day
    before: timedelta  # the video reminder, before the meeting
    ask_again: timedelta  # an unanswered WhatsApp question is asked once more (A47)
    whatsapp: frozenset[WhatsAppNews]  # what may go by WhatsApp


# As the migration writes the row: what the code held until it was a setting.
DEFAULT = Notices(
    quiet=timedelta(minutes=45),
    hold=timedelta(hours=2),
    morning=time(8, 30),
    evening=time(18, 0),
    before=timedelta(minutes=30),
    ask_again=timedelta(days=3),
    whatsapp=frozenset(WhatsAppNews),
)


def from_row(row: NoticeSettings) -> Notices:
    return Notices(
        quiet=timedelta(minutes=row.quiet_minutes),
        hold=timedelta(minutes=row.hold_minutes),
        morning=row.reminder_morning,
        evening=row.reminder_evening,
        before=timedelta(minutes=row.reminder_before_minutes),
        ask_again=timedelta(days=row.ask_again_days),
        whatsapp=frozenset(WhatsAppNews(news) for news in row.whatsapp_news),
    )


async def current(db: AsyncSession) -> Notices:
    row = await db.get(NoticeSettings, 1)
    return DEFAULT if row is None else from_row(row)
