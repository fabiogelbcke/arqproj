import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from run_local import local_environment, read_env


class LocalModes(unittest.TestCase):
    def test_demo_ignores_real_settings_and_missing_env(self):
        with patch.dict(os.environ, {'GOOGLE_SERVICE_ACCOUNT_KEY': 'private', 'DRIVE_API_BASE': 'https://example.com', 'DASHBOARD_PASSWORD': 'private'}):
            env = local_environment('test', Path('/nonexistent/.env'))
        for key in ('GOOGLE_SERVICE_ACCOUNT_KEY', 'DRIVE_API_BASE', 'DASHBOARD_PASSWORD'):
            self.assertNotIn(key, env)

    def test_drive_requires_configuration(self):
        with self.assertRaisesRegex(ValueError, 'Missing .env'):
            local_environment('drive', Path('/nonexistent/.env'))

    def test_literal_settings_and_local_auth(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / '.env'
            path.write_text('export DRIVE_ROOT_FOLDER_ID=folder\nGOOGLE_APPLICATION_CREDENTIALS="/path with spaces/key.json"\nDASHBOARD_PASSWORD=\'$(do-not-execute)\'\nDRIVE_API_BASE=http://fake\nK_SERVICE=production\n')
            env = local_environment('drive', path)
            self.assertEqual(env['GOOGLE_APPLICATION_CREDENTIALS'], '/path with spaces/key.json')
            self.assertEqual(env['DASHBOARD_PASSWORD'], '$(do-not-execute)')
            self.assertNotIn('DRIVE_API_BASE', env)
            self.assertNotIn('K_SERVICE', env)
            path.write_text('DASHBOARD_PASSWORD="private\n')
            with self.assertRaisesRegex(ValueError, '^Invalid quoting in .env at line 1$'):
                read_env(path)


class DriveModes(unittest.TestCase):
    BASE = ('GOOGLE_APPLICATION_CREDENTIALS=/k.json\nDRIVE_ROOT_FOLDER_ID=folder\n'
            'OAUTH_CLIENT_ID=cid\nOAUTH_CLIENT_SECRET=secret\n'
            'OAUTH_REDIRECT_URI=http://127.0.0.1:5000/painel/drive/callback\n'
            'PORTAL_STATE_BUCKET=prod-bucket\nPROJECTS_SOURCE=connection\n')

    def env(self, mode, text=BASE, port=5000):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / '.env'
            path.write_text(text)
            return local_environment(mode, path, port)

    def test_drive_mode_reads_the_configured_folder_without_oauth(self):
        env = self.env('drive')
        self.assertEqual(env['DRIVE_ROOT_FOLDER_ID'], 'folder')
        for key in ('OAUTH_CLIENT_ID', 'OAUTH_CLIENT_SECRET', 'OAUTH_REDIRECT_URI',
                    'PROJECTS_SOURCE', 'PORTAL_STATE_BUCKET'):
            self.assertNotIn(key, env)

    def test_drive_oauth_mode_reads_the_connected_folder(self):
        env = self.env('drive-oauth')
        self.assertEqual(env['PROJECTS_SOURCE'], 'connection')
        self.assertEqual(env['OAUTH_CLIENT_ID'], 'cid')
        self.assertNotIn('DRIVE_ROOT_FOLDER_ID', env)
        self.assertNotIn('PORTAL_STATE_BUCKET', env)  # never the production connection

    def test_drive_oauth_needs_the_oauth_client(self):
        with self.assertRaisesRegex(ValueError, 'OAUTH_CLIENT_SECRET'):
            self.env('drive-oauth', self.BASE.replace('OAUTH_CLIENT_SECRET=secret\n', ''))

    def test_drive_oauth_redirect_must_match_the_port(self):
        with self.assertRaisesRegex(ValueError, '127.0.0.1:5001/painel/drive/callback'):
            self.env('drive-oauth', port=5001)
