import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from arq.projects import Project


class ProjectUpdates(unittest.TestCase):
    def test_recent_files_are_sorted_limited_and_linked_to_their_stage(self):
        stage = SimpleNamespace(entries=[SimpleNamespace(file=SimpleNamespace(
            name=f'Arquivo {day}.pdf', modified=datetime(2026, 10, day, tzinfo=timezone.utc)))
            for day in [1, 5, 2, 4, 3]])
        project = Project(SimpleNamespace(), [stage])
        self.assertEqual([file.name for file, _ in project.recent_files],
                         ['Arquivo 5.pdf', 'Arquivo 4.pdf', 'Arquivo 3.pdf'])
        self.assertTrue(all(parent is stage for _, parent in project.recent_files))

    def test_undated_files_are_not_presented_as_recent_updates(self):
        stage = SimpleNamespace(entries=[SimpleNamespace(file=SimpleNamespace(modified=None))])
        self.assertEqual(Project(SimpleNamespace(), [stage]).recent_files, [])
        self.assertEqual(Project(SimpleNamespace(), []).recent_files, [])
