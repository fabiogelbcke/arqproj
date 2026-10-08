"""Manage editable demo data; regeneration preserves the previous directory."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / 'local-test-data'
MARKER = '.fixture-version.json'


def fixture_version():
    digest = hashlib.sha256()
    for name in ('fake_drive.py', 'export_sample.py', 'local_data.py'):
        digest.update((ROOT / 'tools' / name).read_bytes())
    return digest.hexdigest()


def outdated(folder):
    try:
        return json.loads((folder / MARKER).read_text()).get('version') != fixture_version()
    except (OSError, ValueError, AttributeError):
        return True


def regenerate(folder):
    """Build first, then move the old directory intact to a unique backup."""
    from tools.export_sample import write
    from tools.fake_drive import FakeDrive

    folder = Path(folder).absolute()
    if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
        raise ValueError('Dataset must be a directory, not a symlink or file.')
    if folder == ROOT or ROOT.is_relative_to(folder):
        raise ValueError('Choose a dedicated dataset directory, not the repository or its parents.')
    folder.parent.mkdir(parents=True, exist_ok=True)
    lock = folder.parent / ('.' + folder.name + '.lock')
    try:
        lock.mkdir()
    except FileExistsError:
        raise ValueError('Another generation may be running; dataset lock already exists.') from None
    staging = None
    backup = None
    try:
        staging = Path(tempfile.mkdtemp(prefix='.' + folder.name + '-', dir=folder.parent))
        fake = FakeDrive('http://unused')
        write(fake.nodes[fake.root_id], fake, str(staging))
        (staging / MARKER).write_text(json.dumps({'version': fixture_version()}, indent=2) + '\n')
        if folder.exists():
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            backup = folder.with_name(folder.name + '-backup-' + stamp + '-' + uuid.uuid4().hex[:8])
            folder.rename(backup)
            if not backup.is_dir() or folder.exists():
                raise OSError('Could not verify the dataset backup.')
        try:
            staging.rename(folder)
        except OSError:
            if backup is not None and not folder.exists():
                backup.rename(folder)
            raise
        staging = None
        return backup
    finally:
        if staging is not None:
            shutil.rmtree(staging)
        lock.rmdir()


def prepare(folder, choice=None):
    folder = Path(folder).absolute()
    if folder.exists() and choice is None:
        if outdated(folder):
            print('Updated sample fixtures are available (or this dataset has no version). Regeneration is recommended.')
        try:
            answer = input('Reuse existing test files or regenerate defaults? [reuse/regenerate]: ').strip().lower()
        except EOFError:
            raise ValueError('Choose --reuse-data or --regenerate-data; no files were changed.') from None
        if answer not in ('reuse', 'regenerate'):
            raise ValueError('Choose reuse or regenerate; no files were changed.')
        choice = answer
    if not folder.exists() or choice == 'regenerate':
        backup = regenerate(folder)
        if backup:
            print(f'Previous dataset preserved at: {backup}', flush=True)
    elif outdated(folder):
        print('Using existing files; defaults have changed or the dataset version is unknown.')
    if not (folder / 'Projects').is_dir():
        raise ValueError(f'Missing Projects folder in {folder}. Choose regeneration to create defaults.')
    return folder / 'Projects'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=DEFAULT_DATA)
    parser.add_argument('--regenerate', action='store_true', help='Explicitly regenerate, backing up existing files first')
    args = parser.parse_args()
    try:
        path = prepare(args.data_dir, 'regenerate' if args.regenerate else None)
    except (ValueError, OSError) as error:
        parser.exit(2, f'{error}\n')
    print(f'Editable project files: {path}')


if __name__ == '__main__':
    main()
