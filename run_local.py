"""Run locally with test data, or against Google Drive with your private .env.

  test        editable local files, plus a fake Google sign-in for the painel
  drive       projects from DRIVE_ROOT_FOLDER_ID, read with the service account
  drive-oauth projects from the folder created when you connect Google Drive in
              the painel (real Google sign-in), still read with the service account
"""
import argparse
import os
from pathlib import Path
import re
import shlex
from urllib.parse import urlparse
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
APP_SETTINGS = {
    'GOOGLE_APPLICATION_CREDENTIALS', 'GOOGLE_SERVICE_ACCOUNT_KEY',
    'DRIVE_ROOT_FOLDER_ID', 'DRIVE_API_BASE', 'SITE_NAME', 'SITE_LANG',
    'SITE_TIMEZONE', 'CACHE_TTL_SECONDS', 'SHOW_PROJECT_INDEX', 'NEW_BADGE_DAYS',
    'DASHBOARD_PASSWORD', 'USE_METADATA_SERVER', 'METADATA_TOKEN_URL',
    'K_SERVICE', 'DEBUG', 'PORT', 'FAKE_DRIVE_PORT', 'LOCAL_TEST_PROJECTS',
    'OAUTH_CLIENT_ID', 'OAUTH_CLIENT_SECRET', 'OAUTH_REDIRECT_URI', 'OAUTH_AUTH_URI',
    'OAUTH_TOKEN_URI', 'SERVICE_ACCOUNT_EMAIL', 'PORTAL_STATE_BUCKET', 'PORTAL_STATE_FILE',
    'PORTAL_SETTINGS_FILE', 'PROJECTS_SOURCE',
}
OAUTH_SETTINGS = ('OAUTH_CLIENT_ID', 'OAUTH_CLIENT_SECRET', 'OAUTH_REDIRECT_URI')


def read_env(path):
    """Read literal KEY=value settings; never execute shell commands."""
    result = {}
    for number, line in enumerate(path.read_text().splitlines(), 1):
        try:
            parts = shlex.split(line, comments=True)
        except ValueError:
            raise ValueError(f'Invalid quoting in .env at line {number}') from None
        if parts and parts[0] == 'export':
            parts = parts[1:]
        if not parts:
            continue
        if len(parts) != 1 or '=' not in parts[0]:
            raise ValueError(f'Expected KEY=value in .env at line {number}')
        key, value = parts[0].split('=', 1)
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key):
            raise ValueError(f'Invalid setting name in .env at line {number}')
        result[key] = value
    return result


def local_environment(mode, env_path, port=5000):
    env = {k: v for k, v in os.environ.items() if k not in APP_SETTINGS}
    if mode in ('drive', 'drive-oauth'):
        if not env_path.is_file():
            raise ValueError('Missing .env. See README.md for the local Google Drive setup.')
        settings = read_env(env_path)
        env.update({k: v for k, v in settings.items() if k in APP_SETTINGS})
        if not (env.get('GOOGLE_APPLICATION_CREDENTIALS') or env.get('GOOGLE_SERVICE_ACCOUNT_KEY')):
            raise ValueError('Set GOOGLE_APPLICATION_CREDENTIALS in .env to your credentials file.')
        # Local Drive modes always use Google and explicit local credentials.
        for key in ('DRIVE_API_BASE', 'USE_METADATA_SERVER', 'METADATA_TOKEN_URL', 'K_SERVICE',
                    'OAUTH_AUTH_URI', 'OAUTH_TOKEN_URI', 'PROJECTS_SOURCE'):
            env.pop(key, None)
        # Keep the connection and settings in local files, never a shared bucket.
        env.pop('PORTAL_STATE_BUCKET', None)
    if mode == 'drive':
        if not env.get('DRIVE_ROOT_FOLDER_ID'):
            raise ValueError('Set DRIVE_ROOT_FOLDER_ID in .env.')
        # Read-only: no "Connect Google Drive" in the painel in this mode.
        for key in OAUTH_SETTINGS:
            env.pop(key, None)
    if mode == 'drive-oauth':
        missing = [k for k in OAUTH_SETTINGS if not env.get(k)]
        if missing:
            raise ValueError(f'Set {", ".join(missing)} in .env. See README.md, "Google Drive connection".')
        redirect = urlparse(env['OAUTH_REDIRECT_URI'])
        if redirect.hostname != '127.0.0.1' or redirect.port != port:
            raise ValueError(f'OAUTH_REDIRECT_URI in .env must be http://127.0.0.1:{port}/painel/drive/callback '
                             'for this port, and registered on the OAuth client in Google Cloud.')
        env['PROJECTS_SOURCE'] = 'connection'
        env.pop('DRIVE_ROOT_FOLDER_ID', None)
    env['DEBUG'] = '0'
    env['FLASK_SKIP_DOTENV'] = '1'
    return env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['test', 'drive', 'drive-oauth'])
    parser.add_argument('--port', type=int, default=5000)
    parser.add_argument('--fake-drive-port', type=int, default=8765)
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'local-test-data')
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument('--reuse-data', action='store_true')
    selection.add_argument('--regenerate-data', action='store_true')
    args = parser.parse_args()
    try:
        env = local_environment(args.mode, ROOT / '.env', args.port)
        if args.mode != 'test' and (args.reuse_data or args.regenerate_data):
            raise ValueError('Dataset flags apply only to test mode.')
        if args.mode == 'test':
            from tools.local_data import prepare
            choice = 'reuse' if args.reuse_data else 'regenerate' if args.regenerate_data else None
            projects = prepare(args.data_dir, choice)
            env['LOCAL_TEST_PROJECTS'] = str(projects)
            print(f'Editable files: {projects}\nAfter editing, restart with --reuse-data.', flush=True)
    except (ValueError, OSError) as error:
        parser.exit(2, f'{error}\n')
    env['PORT'] = str(args.port)
    env['FAKE_DRIVE_PORT'] = str(args.fake_drive_port)
    print(f'Local mode: {args.mode} | http://127.0.0.1:{args.port}', flush=True)
    script = 'demo.py' if args.mode == 'test' else 'app.py'
    try:
        return subprocess.call([sys.executable, str(ROOT / script)], cwd=ROOT, env=env)
    except KeyboardInterrupt:
        return 130


if __name__ == '__main__':
    sys.exit(main())
