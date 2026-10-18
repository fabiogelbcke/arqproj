"""A folder on this machine as the file store (`make dev`).

Item ids are paths relative to the root (`Casa Jardim/01 - Briefing/Planta.pdf`);
anything that would leave the root is "not found". Only for local development:
the app refuses this kind of storage when deployed.
"""

from __future__ import annotations

import mimetypes
from datetime import UTC, datetime
from pathlib import Path

import anyio

from backend.storage.base import (
    FOLDER_TYPE,
    Download,
    StorageError,
    StorageItem,
    StorageProblem,
    sorted_items,
)

CHUNK = 256 * 1024


class FolderStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _path(self, item_id: str) -> Path:
        path = (self.root / item_id).resolve()
        if not path.is_relative_to(self.root) or not path.exists():
            raise StorageError(StorageProblem.NOT_FOUND)
        return path

    def _item(self, path: Path) -> StorageItem:
        stat = path.stat()
        is_folder = path.is_dir()
        mime = (
            FOLDER_TYPE
            if is_folder
            else mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        )
        return StorageItem(
            id=path.relative_to(self.root).as_posix() if path != self.root else "",
            name=path.name,
            mime_type=mime,
            size=None if is_folder else stat.st_size,
            modified_at=datetime.fromtimestamp(stat.st_mtime, UTC),
            # The disk's own number for the file: kept through renames and moves.
            stable_id=f"inode:{stat.st_dev}:{stat.st_ino}",
        )

    async def list_folder(self, folder_id: str) -> list[StorageItem]:
        def read() -> list[StorageItem]:
            path = self._path(folder_id)
            if not path.is_dir():
                raise StorageError(StorageProblem.NOT_FOUND)
            return [self._item(child) for child in path.iterdir()]

        return sorted_items(await anyio.to_thread.run_sync(read))

    async def get(self, item_id: str) -> StorageItem:
        return await anyio.to_thread.run_sync(lambda: self._item(self._path(item_id)))

    async def download(self, item: StorageItem) -> Download:
        path = self._path(item.id)
        if path.is_dir():
            raise StorageError(StorageProblem.NOT_FOUND)

        async def chunks():
            async with await anyio.open_file(path, "rb") as file:
                while block := await file.read(CHUNK):
                    yield block

        return Download(item.mime_type, path.stat().st_size, chunks())

    async def thumbnail(self, item: StorageItem, size: int = 640) -> bytes | None:
        return None
