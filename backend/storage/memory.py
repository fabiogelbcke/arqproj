"""In-memory storage for automated tests: build a tree, read it back."""

from __future__ import annotations

from datetime import UTC, datetime

from backend.storage.base import (
    FOLDER_TYPE,
    Download,
    StorageError,
    StorageItem,
    StorageProblem,
    sorted_items,
)


class MemoryStorage:
    def __init__(self) -> None:
        self._items: dict[str, StorageItem] = {}
        self._parents: dict[str, str | None] = {}
        self._content: dict[str, bytes] = {}

    def add_folder(self, item_id: str, name: str, parent: str | None = None) -> StorageItem:
        return self._add(StorageItem(item_id, name, FOLDER_TYPE, None, _now()), parent)

    def add_file(
        self, item_id: str, name: str, parent: str, content: bytes, mime_type: str
    ) -> StorageItem:
        self._content[item_id] = content
        return self._add(StorageItem(item_id, name, mime_type, len(content), _now()), parent)

    def _add(self, item: StorageItem, parent: str | None) -> StorageItem:
        self._items[item.id] = item
        self._parents[item.id] = parent
        return item

    async def list_folder(self, folder_id: str) -> list[StorageItem]:
        if folder_id not in self._items or not self._items[folder_id].is_folder:
            raise StorageError(StorageProblem.NOT_FOUND)
        return sorted_items([i for i in self._items.values() if self._parents[i.id] == folder_id])

    async def get(self, item_id: str) -> StorageItem:
        if item_id not in self._items:
            raise StorageError(StorageProblem.NOT_FOUND)
        return self._items[item_id]

    async def download(
        self, item: StorageItem, byte_range: tuple[int, int] | None = None
    ) -> Download:
        if item.id not in self._content:
            raise StorageError(StorageProblem.NOT_FOUND)
        content = self._content[item.id]
        if byte_range is not None:
            content = content[byte_range[0] : byte_range[1] + 1]

        async def chunks():
            yield content

        return Download(item.mime_type, len(content), chunks())

    async def thumbnail(self, item: StorageItem, size: int = 640) -> bytes | None:
        return None


def _now() -> datetime:
    return datetime.now(UTC)
