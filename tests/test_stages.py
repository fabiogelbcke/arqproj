import unittest
import tempfile
from pathlib import Path

from arq.stages import STANDARD_STAGES, stage_explanation
from tools.fake_drive import FakeDrive


class StandardStages(unittest.TestCase):
    def test_all_standard_stages_have_explanations(self):
        self.assertEqual(len(STANDARD_STAGES), 7)
        for number, label in enumerate(STANDARD_STAGES, 1):
            for language in ('pt', 'en'):
                summary, delivery = stage_explanation(number, label, language)
                self.assertTrue(summary)
                self.assertTrue(delivery)

    def test_custom_stages_do_not_get_incorrect_explanations(self):
        self.assertIsNone(stage_explanation(1, 'Briefing', 'pt'))
        self.assertIsNone(stage_explanation(None, 'Proposta', 'pt'))
        self.assertIsNone(stage_explanation(8, 'Proposta', 'pt'))

    def test_standard_fixture_has_only_the_seven_stages(self):
        drive = FakeDrive('http://unused')
        project = next(n for n in drive.nodes.values() if n.name == 'Projeto Padrão')
        folders = [n.name for n in project.children if n.mime == 'application/vnd.google-apps.folder']
        self.assertEqual(folders, [f'{n:02d} - {label}' for n, label in enumerate(STANDARD_STAGES, 1)])

    def test_export_keeps_slash_stage_at_one_folder_level(self):
        from tools.export_sample import write
        drive = FakeDrive('http://unused')
        project = next(n for n in drive.nodes.values() if n.name == 'Projeto Padrão')
        with tempfile.TemporaryDirectory() as temp:
            write(project, drive, temp)
            folders = [p for p in (Path(temp) / 'Projeto Padrão').iterdir() if p.is_dir()]
            self.assertEqual(len(folders), 7)
            self.assertTrue((Path(temp) / 'Projeto Padrão' / '03 - Estudos Preliminares - Anteprojeto').is_dir())
