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
        self.actual_thumbnails = {}
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
            # Actual first-page PDF previews in local mode; image bytes are served directly.
            if mime == 'application/pdf':
                try:
                    import fitz
                    with fitz.open(stream=node.content, filetype='pdf') as document:
                        if document.page_count:
                            page = document[0]
                            scale = 440 / max(page.rect.width, page.rect.height)
                            self.actual_thumbnails[file_id] = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False).tobytes('png')
                            node.thumb = True
                except (ImportError, RuntimeError, ValueError):
                    pass  # Invalid/unsupported documents retain their file icon.
            self.nodes[file_id] = node
            if parent:
                parent.children.append(node)
            if directory:
                for child in sorted(path.iterdir()):
                    visit(child, node)
            return node

        return visit(self.folder).id
