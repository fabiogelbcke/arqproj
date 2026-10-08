"""Run locally with generated test data or private .env Drive settings."""
import argparse
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
APP_SETTINGS = {
    'GOOGLE_APPLICATION_CREDENTIALS', 'GOOGLE_SERVICE_ACCOUNT_KEY',
    'DRIVE_ROOT_FOLDER_ID', 'DRIVE_API_BASE', 'SITE_NAME', 'SITE_LANG',
    'SITE_TIMEZONE', 'CACHE_TTL_SECONDS', 'SHOW_PROJECT_INDEX', 'NEW_BADGE_DAYS',
    'DASHBOARD_PASSWORD', 'USE_METADATA_SERVER', 'METADATA_TOKEN_URL',
    'K_SERVICE', 'DEBUG', 'PORT', 'FAKE_DRIVE_PORT',
}


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


def local_environment(mode, env_path):
    env = {k: v for k, v in os.environ.items() if k not in APP_SETTINGS}
    if mode == 'drive':
        if not env_path.is_file():
            raise ValueError('Missing .env. See README.md for the local Google Drive setup.')
        settings = read_env(env_path)
        env.update({k: v for k, v in settings.items() if k in APP_SETTINGS})
        if not env.get('DRIVE_ROOT_FOLDER_ID'):
            raise ValueError('Set DRIVE_ROOT_FOLDER_ID in .env.')
        if not (env.get('GOOGLE_APPLICATION_CREDENTIALS') or env.get('GOOGLE_SERVICE_ACCOUNT_KEY')):
            raise ValueError('Set GOOGLE_APPLICATION_CREDENTIALS in .env to your credentials file.')
        # Local Drive mode always uses Google and explicit local credentials.
        for key in ('DRIVE_API_BASE', 'USE_METADATA_SERVER', 'METADATA_TOKEN_URL', 'K_SERVICE'):
            env.pop(key, None)
    env['DEBUG'] = '0'
    return env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['test', 'drive'])
    parser.add_argument('--port', type=int, default=5000)
    parser.add_argument('--fake-drive-port', type=int, default=8765)
    args = parser.parse_args()
    try:
        env = local_environment(args.mode, ROOT / '.env')
    except ValueError as error:
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
