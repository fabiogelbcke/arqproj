"""Meeting settings and Google Calendar links, without calendar account access."""
from datetime import datetime, timezone
import os
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from arq.config import parse_config


class MeetingConfig(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, SITE_TIMEZONE='America/Sao_Paulo', SITE_LANG='pt')
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_portuguese_fields_and_calendar_time(self):
        cfg = parse_config('Reunião agendada: 20/10/2026 14:00\nFim da reunião: 20/10/2026 15:30\n'
                           'Assunto da reunião: Layout & materiais\nLocal da reunião: Estúdio\n'
                           'Link da reunião: https://meet.google.com/abc-defg-hij\n\nDescrição.')
        self.assertFalse(cfg.issues)
        self.assertEqual(cfg.details, [])
        self.assertEqual(cfg.meeting.start.hour, 14)
        self.assertEqual(cfg.meeting.timezone_label, 'horário de Brasília')
        params = parse_qs(urlsplit(cfg.meeting.calendar_url('Casa')).query)
        self.assertEqual(params['dates'], ['20261020T170000Z/20261020T183000Z'])
        self.assertEqual(params['text'], ['Layout & materiais'])
        self.assertEqual(params['location'], ['Estúdio'])
        self.assertEqual(params['details'], ['https://meet.google.com/abc-defg-hij'])
        self.assertEqual(params['ctz'], ['America/Sao_Paulo'])

    def test_defaults_and_iso_offset(self):
        cfg = parse_config('Meeting start: 2026-10-20T17:00:00+00:00')
        self.assertEqual(cfg.meeting.start.hour, 14)
        self.assertEqual(cfg.meeting.end.hour, 15)
        params = parse_qs(urlsplit(cfg.meeting.calendar_url('Casa & Jardim')).query)
        self.assertEqual(params['text'], ['Reunião do projeto · Casa & Jardim'])
        self.assertNotIn('details', params)

    def test_invalid_or_incomplete_settings(self):
        for text in ('Reunião agendada: 2026-10-20', 'Reunião agendada: 31/02/2026 14:00',
                     'Assunto da reunião: Layout',
                     'Reunião agendada: 2026-10-20 14:00\nFim da reunião: 2026-10-20 13:00',
                     'Reunião agendada: 2026-10-20 14:00\nLink da reunião: javascript:alert(1)',
                     'Reunião agendada: 2026-10-20 14:00\nLink da reunião: https://user:pass@example.com'):
            with self.subTest(text=text):
                cfg = parse_config(text)
                self.assertIsNone(cfg.meeting)
                self.assertEqual(cfg.issues[0][0], 'cfg.invalid_meeting')

    def test_missing_and_finished_meetings(self):
        self.assertIsNone(parse_config('Title: Casa').meeting)
        cfg = parse_config('Meeting start: 2026-10-20 14:00')
        with patch('arq.i18n.now', return_value=datetime(2026, 10, 20, 18, tzinfo=timezone.utc)):
            self.assertFalse(cfg.meeting.upcoming)
        with patch('arq.i18n.now', return_value=datetime(2026, 10, 20, 17, 30, tzinfo=timezone.utc)):
            self.assertTrue(cfg.meeting.upcoming)

    def test_icalendar_dates_escaping_and_utf8_folding(self):
        meeting = parse_config('Meeting start: 2026-10-20 14:00').meeting
        meeting.title = 'Apresentação, layout; ' + 'á' * 70 + '\nNova linha'
        meeting.location = 'Estúdio, sala 1'
        meeting.link = 'https://meet.google.com/abc-defg-hij'
        raw = meeting.icalendar('Casa', 'project-123')
        lines = raw.decode('utf-8').split('\r\n')
        self.assertTrue(all(len(line.encode('utf-8')) <= 75 for line in lines))
        text = raw.decode('utf-8').replace('\r\n ', '')
        self.assertIn('DTSTART:20261020T170000Z\r\n', text)
        self.assertIn('DTEND:20261020T180000Z\r\n', text)
        self.assertIn('SUMMARY:Apresentação\\, layout\\; ', text)
        self.assertIn('\\nNova linha', text)
        self.assertIn('LOCATION:Estúdio\\, sala 1', text)
        self.assertIn('DESCRIPTION:https://meet.google.com/abc-defg-hij', text)
        self.assertTrue(text.endswith('END:VCALENDAR\r\n'))
