"""Project meeting dates and a Google Calendar event template."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlsplit
from uuid import NAMESPACE_URL, uuid5

from . import i18n


def parse_datetime(value: str) -> datetime:
    # A time is required: a date alone must not silently become midnight.
    if len(value.strip()) <= 10:
        raise ValueError('Use YYYY-MM-DD HH:MM or DD/MM/YYYY HH:MM.')
    try:
        result = datetime.fromisoformat(value.strip())
    except ValueError:
        try:
            result = datetime.strptime(value.strip(), '%d/%m/%Y %H:%M')
        except ValueError:
            raise ValueError('Use YYYY-MM-DD HH:MM or DD/MM/YYYY HH:MM.') from None
    return (result.replace(tzinfo=i18n.site_tz()) if result.tzinfo is None else result).astimezone(i18n.site_tz())


@dataclass
class Meeting:
    start: datetime
    end: datetime
    title: str | None = None
    location: str | None = None
    link: str | None = None

    @property
    def upcoming(self) -> bool:
        return self.end > i18n.now()

    @property
    def timezone_label(self) -> str:
        if str(self.start.tzinfo) == 'America/Sao_Paulo':
            return i18n.t('meeting.brasilia')
        offset = self.start.strftime('%z')
        return f'UTC{offset[:3]}:{offset[3:]}'

    def calendar_url(self, project_title: str) -> str:
        title = self.title or i18n.t('meeting.default_title', project=project_title)
        params = {
            'action': 'TEMPLATE', 'text': title,
            'dates': '/'.join(dt.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ') for dt in (self.start, self.end)),
            'ctz': str(i18n.site_tz()),
        }
        if self.location:
            params['location'] = self.location
        if self.link:
            params['details'] = self.link
        return 'https://calendar.google.com/calendar/render?' + urlencode(params)

    def icalendar(self, project_title: str, project_id: str) -> bytes:
        def escape(value):
            return value.replace('\\', '\\\\').replace('\r\n', '\n').replace('\r', '\n').replace('\n', '\\n').replace(';', '\\;').replace(',', '\\,')

        def stamp(value):
            return value.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')

        lines = [
            'BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Arq Portal//Project Meeting//PT',
            'CALSCALE:GREGORIAN', 'BEGIN:VEVENT',
            f'UID:{uuid5(NAMESPACE_URL, project_id + self.start.isoformat())}@arq-portal',
            f'DTSTAMP:{stamp(i18n.now())}', f'DTSTART:{stamp(self.start)}', f'DTEND:{stamp(self.end)}',
            'SUMMARY:' + escape(self.title or i18n.t('meeting.default_title', project=project_title)),
        ]
        if self.location:
            lines.append('LOCATION:' + escape(self.location))
        if self.link:
            lines.append('DESCRIPTION:' + escape(self.link))
        lines += ['END:VEVENT', 'END:VCALENDAR']
        # RFC 5545 limits content lines to 75 UTF-8 octets; never split a character.
        folded = []
        for line in lines:
            part = ''
            for char in line:
                if len((part + char).encode('utf-8')) > 75:
                    folded.append(part)
                    part = ' '
                part += char
            folded.append(part)
        return ('\r\n'.join(folded) + '\r\n').encode('utf-8')


def build_meeting(start, end=None, title=None, location=None, link=None) -> Meeting | None:
    if not any((start, end, title, location, link)):
        return None
    if not start:
        raise ValueError('Meeting start date and time are required.')
    start_dt = parse_datetime(start)
    end_dt = parse_datetime(end) if end else (start_dt.astimezone(timezone.utc) + timedelta(hours=1)).astimezone(i18n.site_tz())
    if end_dt.astimezone(timezone.utc) <= start_dt.astimezone(timezone.utc):
        raise ValueError('Meeting end must be after its start.')
    if link:
        parsed = urlsplit(link)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('Meeting link must be an HTTPS URL.')
    return Meeting(start_dt, end_dt, title, location, link)
