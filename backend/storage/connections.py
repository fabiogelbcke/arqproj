"""The file store for an office's connection."""

from __future__ import annotations

from pathlib import Path

from backend.settings import Settings
from backend.storage.base import Storage
from backend.storage.folder import FolderStorage
from backend.storage.google import GoogleDriveStorage
from backend.storage.models import StorageConnection, StorageKind


def storage_for(
    connection: StorageConnection, settings: Settings, google: GoogleDriveStorage
) -> Storage:
    if connection.kind is StorageKind.GOOGLE:
        return google
    # A folder on this machine: never when deployed, where it would expose the
    # server's own files.
    if settings.deployed:
        raise RuntimeError("folder storage is for local development only")
    return FolderStorage(Path(settings.local_storage_root) / connection.root_id)
