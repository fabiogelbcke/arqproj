"""Expose an editable folder through the existing fake Drive HTTP API.

A snapshot is loaded at startup. Restart with --reuse-data after edits.
"""
from datetime import datetime, timezone
import hashlib
import mimetypes
from pathlib import Path

from tools.fake_drive import FOLDER, FakeDrive, Node


class FolderDrive(FakeDrive):
    def __init__(self, base_url, folder):
        self.folder = Path(folder).absolute()
        super().__init__(base_url)

    def _build(self):
        if not self.folder.is_dir() or self.folder.is_symlink():
            raise ValueError('Local Projects folder must be a regular directory.')

        def visit(path, parent=None):
            # Do not expose files outside the dataset through symlinks.
            if path.is_symlink():
                return
            relative = path.relative_to(self.folder).as_posix()
            file_id = 'local-' + hashlib.sha256(relative.encode()).hexdigest()[:32]
            directory = path.is_dir()
            if not directory and not path.is_file():
                return
            mime = FOLDER if directory else (mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
            node = Node(file_id, path.name, mime, parent.id if parent else None,
                        datetime.fromtimestamp(path.stat().st_mtime, timezone.utc),
                        content=b'' if directory else path.read_bytes())
            # No synthetic thumbnails: the app serves actual image bytes.
            self.nodes[file_id] = node
            if parent:
                parent.children.append(node)
            if directory:
                for child in sorted(path.iterdir()):
                    visit(child, node)
            return node

        return visit(self.folder).id
