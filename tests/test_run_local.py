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
