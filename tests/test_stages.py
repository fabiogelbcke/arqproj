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
                if number not in (2, 3, 4, 5, 6):
                    self.assertTrue(summary)
                self.assertTrue(delivery)

    def test_custom_stages_do_not_get_incorrect_explanations(self):
        self.assertIsNone(stage_explanation(1, 'Briefing', 'pt'))
        self.assertIsNone(stage_explanation(None, 'Proposta', 'pt'))
        self.assertIsNone(stage_explanation(8, 'Proposta', 'pt'))

    def test_second_stage_has_requested_deliverables(self):
        summary, delivery = stage_explanation(2, STANDARD_STAGES[1], 'pt')
        self.assertEqual(summary, '')
        self.assertEqual(delivery.splitlines(), ['Briefing', 'Conceito', 'Pesquisa', 'Moodboard', 'Levantamento técnico'])

    def test_third_stage_has_separate_activities_and_deliverables(self):
        from arq.projects import Stage
        from unittest.mock import patch
        stage = Stage('fictional', 3, STANDARD_STAGES[2], [])
        with patch('arq.i18n.lang', return_value='pt'):
            self.assertEqual(stage.activities, ('Estudo de layout', 'Distribuição dos ambientes',
                'Estudos de mobiliário', 'Definição dos fluxos', 'Primeiras definições de materiais'))
            self.assertEqual(stage.explanation[1].splitlines(), ['Plantas humanizadas', 'Moodboard', 'Imagens de referência'])

    def test_fourth_stage_has_modeling_activities(self):
        from arq.projects import Stage
        from unittest.mock import patch
        stage = Stage('fictional', 4, STANDARD_STAGES[3], [])
        with patch('arq.i18n.lang', return_value='pt'):
            self.assertEqual(stage.activities, ('Modelagem tridimensional', 'Volumetrias', 'Aplicação de materiais'))
            self.assertEqual(stage.explanation[1], 'Imagens realistas')

    def test_executive_stage_has_requested_deliverables(self):
        summary, delivery = stage_explanation(5, STANDARD_STAGES[4], 'pt')
        self.assertEqual(summary, '')
        self.assertEqual(delivery.splitlines(), ['Plantas executivas', 'Detalhamento de marcenaria',
            'Forros e paginações', 'Especificações de materiais', 'Memorial descritivo'])

    def test_final_stage_has_requested_description(self):
        summary, delivery = stage_explanation(6, STANDARD_STAGES[5], 'pt')
        self.assertEqual(summary, '')
        self.assertEqual(delivery, 'Projeto completo de esquadrias, marcenaria, iluminação, mobiliário, climatização, entre outros.')

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
