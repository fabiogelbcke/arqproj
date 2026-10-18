"""The file store for an office's connection."""

from __future__ import annotations

from pathlib import Path

from backend.settings import Settings
from backend.storage.base import Storage, StorageError, StorageProblem
from backend.storage.folder import FolderStorage
from backend.storage.google import GoogleDriveStorage, OfficeDrive
from backend.storage.models import StorageConnection, StorageKind, WriterStatus


def storage_for(
    connection: StorageConnection, settings: Settings, google: GoogleDriveStorage
) -> Storage:
    if connection.kind is StorageKind.GOOGLE:
        # Disconnecting stops both paths at once (plan section 9): the reader may
        # still have Google's permission, but the app no longer uses it. The
        # folder is kept for a reconnect. (Expired is different: pages keep working.)
        if connection.writer_status is WriterStatus.NONE:
            raise StorageError(StorageProblem.NO_ACCESS, "office disconnected Drive")
        # Only this office's folder, never just "whatever the reader can see".
        return OfficeDrive(google, connection.root_id)
    # A folder on this machine: never when deployed, where it would expose the
    # server's own files.
    if settings.deployed:
        raise RuntimeError("folder storage is for local development only")
    return FolderStorage(Path(settings.local_storage_root) / connection.root_id)
