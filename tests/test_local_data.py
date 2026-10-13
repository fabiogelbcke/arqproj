import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.folder_drive import FolderDrive
from tools.fake_drive import TOKEN
from tools.local_data import MARKER, outdated, prepare, regenerate


class LocalDataset(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name) / 'dataset'

    def test_generate_reuse_and_backup_preserve_manual_edits(self):
        projects = prepare(self.folder)
        config = projects / 'Casa Jardim' / '_project.txt'
        self.assertTrue(config.is_file())
        self.assertFalse(outdated(self.folder))
        config.write_text('Title: My manual edits\nSlug: custom\n')
        custom = projects / 'custom.pdf'
        custom.write_bytes(b'manual document')
        prepare(self.folder, 'reuse')
        self.assertEqual(custom.read_bytes(), b'manual document')
        backup = regenerate(self.folder)
        self.assertEqual((backup / 'Projects/custom.pdf').read_bytes(), b'manual document')
        self.assertIn('My manual edits', (backup / 'Projects/Casa Jardim/_project.txt').read_text(encoding='utf-8'))
        self.assertFalse((self.folder / 'Projects/custom.pdf').exists())
        self.assertIn('Casa Jardim', config.read_text(encoding='utf-8'))
        second_backup = regenerate(self.folder)
        self.assertNotEqual(backup, second_backup)
        self.assertTrue(backup.is_dir())

    def test_prompt_eof_and_version_change(self):
        prepare(self.folder)
        (self.folder / MARKER).write_text(json.dumps({'version': 'older'}))
        self.assertTrue(outdated(self.folder))
        with patch('builtins.input', side_effect=EOFError), self.assertRaisesRegex(ValueError, 'Choose --reuse'):
            prepare(self.folder)
        with patch('builtins.input', return_value='reuse') as prompt:
            prepare(self.folder)
            prompt.assert_called_once()
        self.assertTrue(outdated(self.folder))

    def test_generation_failure_does_not_touch_existing_data(self):
        self.folder.mkdir()
        (self.folder / 'keep.txt').write_text('keep me')
        with patch('tools.export_sample.write', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                regenerate(self.folder)
        self.assertEqual((self.folder / 'keep.txt').read_text(encoding='utf-8'), 'keep me')
        self.assertFalse(list(self.folder.parent.glob('dataset-backup-*')))

    def test_backup_failure_does_not_replace_dataset(self):
        self.folder.mkdir()
        (self.folder / 'keep.txt').write_text('keep me')
        with patch.object(Path, 'rename', side_effect=OSError('backup blocked')):
            with self.assertRaises(OSError):
                regenerate(self.folder)
        self.assertEqual((self.folder / 'keep.txt').read_text(encoding='utf-8'), 'keep me')

    def test_failed_install_restores_original(self):
        self.folder.mkdir()
        (self.folder / 'keep.txt').write_text('keep me')
        original = Path.rename
        def rename(path, target):
            if path.name.startswith('.dataset-'):
                raise OSError('install failed')
            return original(path, target)
        with patch.object(Path, 'rename', rename), self.assertRaises(OSError):
            regenerate(self.folder)
        self.assertEqual((self.folder / 'keep.txt').read_text(encoding='utf-8'), 'keep me')

    def test_folder_api_reads_real_bytes_and_stable_ids(self):
        projects = self.folder / 'Projects'
        stage = projects / 'Example' / '01 - Plans'
        stage.mkdir(parents=True)
        doc = stage / 'plan.pdf'
        doc.write_bytes(b'%PDF-manual')
        outside = Path(self.temp.name) / 'private.txt'
        outside.write_text('not public')
        (stage / 'linked.txt').symlink_to(outside)
        fake = FolderDrive('http://localhost', projects)
        node = next(n for n in fake.nodes.values() if n.name == 'plan.pdf')
        self.assertFalse(any(n.name == 'linked.txt' for n in fake.nodes.values()))
        client = fake.app().test_client()
        headers = {'Authorization': 'Bearer ' + TOKEN}
        response = client.get('/drive/v3/files/' + node.id + '?alt=media', headers=headers)
        self.assertEqual(response.data, b'%PDF-manual')
        self.assertEqual(response.mimetype, 'application/pdf')
        self.assertEqual(client.get('/drive/v3/files/' + node.id + '?alt=media').status_code, 401)
        doc.write_bytes(b'%PDF-edited')
        (stage / 'aaa.txt').write_text('new sibling')
        restarted = FolderDrive('http://localhost', projects)
        self.assertEqual(restarted.nodes[node.id].content, b'%PDF-edited')

    def test_reject_symlink_dataset(self):
        target = Path(self.temp.name) / 'target'
        target.mkdir()
        self.folder.symlink_to(target, target_is_directory=True)
        with self.assertRaises(ValueError):
            regenerate(self.folder)

    def test_website_renders_folder_data_and_downloads(self):
        from threading import Thread
        from werkzeug.serving import make_server
        from arq.google_auth import ServiceAccountAuth
        from arq.drive import Drive
        from arq.projects import ProjectStore
        from app import create_app

        projects = prepare(self.folder)
        config = projects / 'Casa Jardim/_project.txt'
        config.write_text(config.read_text(encoding='utf-8').replace('Título: Casa Jardim', 'Título: Editado localmente'), encoding='utf-8')
        stage = projects / 'Casa Jardim/03 - Anteprojeto'
        (stage / 'Manual.pdf').write_bytes(b'%PDF-custom-document')
        fake = FolderDrive('http://127.0.0.1', projects)
        server = make_server('127.0.0.1', 0, fake.app(), threaded=True)
        fake.base_url = f'http://127.0.0.1:{server.server_port}'
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            auth = ServiceAccountAuth(fake.service_account_info())
            store = ProjectStore(Drive(auth, fake.base_url + '/drive/v3'), fake.root_id)
            client = create_app(store).test_client()
            response = client.get('/casa-jardim')
            self.assertEqual(response.status_code, 200)
            html = response.get_data(as_text=True)
            for expected in ('Editado localmente', 'Manual.pdf', 'Plantas – rev B.pdf'):
                self.assertIn(expected, html)
            self.assertNotIn('Fees.xlsx', html)
            node = next(n for n in fake.nodes.values() if n.name == 'Manual.pdf')
            download = client.get('/casa-jardim/f/' + node.id)
            self.assertEqual(download.status_code, 200)
            self.assertEqual(download.data, b'%PDF-custom-document')
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
