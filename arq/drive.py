"""Minimal Drive v3 REST client: list folders, read text, stream files."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime

import requests

from .google_auth import ServiceAccountAuth

FOLDER = "application/vnd.google-apps.folder"
SHORTCUT = "application/vnd.google-apps.shortcut"
NATIVE_PREFIX = "application/vnd.google-apps."
GOOGLE_DOC = "application/vnd.google-apps.document"

# Google-native types we can hand to clients as PDF.
PDF_EXPORTABLE = {
    "application/vnd.google-apps.document",
    "application/vnd.google-apps.spreadsheet",
    "application/vnd.google-apps.presentation",
    "application/vnd.google-apps.drawing",
}

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,}$")
_LIST_FIELDS = (
    "nextPageToken,files(id,name,mimeType,size,modifiedTime,"
    "hasThumbnail,thumbnailLink,shortcutDetails)"
)


class DriveError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class NotDownloadable(RuntimeError):
    pass


@dataclass
class DriveFile:
    id: str
    name: str
    mime_type: str
    size: int | None = None
    modified: datetime | None = None
    thumbnail_link: str | None = None

    @property
    def is_folder(self) -> bool:
        return self.mime_type == FOLDER

    @property
    def is_native(self) -> bool:
        return self.mime_type.startswith(NATIVE_PREFIX)

    @classmethod
    def from_api(cls, d: dict) -> "DriveFile":
        file_id, mime = d["id"], d.get("mimeType", "")
        # Shortcuts behave like their target (a shortcut to a folder is a folder).
        if mime == SHORTCUT and d.get("shortcutDetails"):
            file_id = d["shortcutDetails"].get("targetId", file_id)
            mime = d["shortcutDetails"].get("targetMimeType", mime)
        modified = d.get("modifiedTime")
        return cls(
            id=file_id,
            name=d.get("name", ""),
            mime_type=mime,
            size=int(d["size"]) if d.get("size") else None,
            modified=datetime.fromisoformat(modified.replace("Z", "+00:00")) if modified else None,
            thumbnail_link=d.get("thumbnailLink") if d.get("hasThumbnail", True) else None,
        )


class Drive:
    def __init__(self, auth: ServiceAccountAuth, base_url: str | None = None):
        self.auth = auth
        self.base = (base_url or os.environ.get("DRIVE_API_BASE") or "https://www.googleapis.com/drive/v3").rstrip("/")
        self.session = requests.Session()

    def _get(self, path: str, params: dict | None = None, *, stream: bool = False) -> requests.Response:
        resp = self.session.get(
            self.base + path,
            params=params,
            headers={"Authorization": f"Bearer {self.auth.token()}"},
            stream=stream,
            timeout=(10, 60),
        )
        if not resp.ok:
            body = "" if stream else resp.text[:300]
            resp.close()
            raise DriveError(resp.status_code, f"Drive {resp.status_code} on {path}: {body}")
        return resp

    @staticmethod
    def _check_id(file_id: str) -> str:
        if not _ID_RE.match(file_id or ""):
            raise ValueError(f"invalid Drive id: {file_id!r}")
        return file_id

    def list_children(self, folder_id: str) -> list[DriveFile]:
        self._check_id(folder_id)
        out: list[DriveFile] = []
        params = {
            "q": f"'{folder_id}' in parents and trashed = false",
            "fields": _LIST_FIELDS,
            "pageSize": "1000",
            "orderBy": "name",
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }
        while True:
            data = self._get("/files", params).json()
            out.extend(DriveFile.from_api(f) for f in data.get("files", []))
            token = data.get("nextPageToken")
            if not token:
                return out
            params["pageToken"] = token

    def read_text(self, f: DriveFile) -> str:
        self._check_id(f.id)
        if f.mime_type == GOOGLE_DOC:
            resp = self._get(f"/files/{f.id}/export", {"mimeType": "text/plain"})
        else:
            resp = self._get(f"/files/{f.id}", {"alt": "media", "supportsAllDrives": "true"})
        return resp.content.decode("utf-8-sig", errors="replace")

    def open_media(self, f: DriveFile) -> tuple[requests.Response, str, str]:
        """Returns (streaming response, content type, download filename)."""
        self._check_id(f.id)
        if f.is_native:
            if f.mime_type not in PDF_EXPORTABLE:
                raise NotDownloadable(f.mime_type)
            resp = self._get(f"/files/{f.id}/export", {"mimeType": "application/pdf"}, stream=True)
            return resp, "application/pdf", f"{f.name}.pdf"
        resp = self._get(f"/files/{f.id}", {"alt": "media", "supportsAllDrives": "true"}, stream=True)
        return resp, f.mime_type or "application/octet-stream", f.name

    def open_thumbnail(self, f: DriveFile, size: int = 640) -> requests.Response | None:
        if not f.thumbnail_link:
            return None
        link = re.sub(r"=s\d+$", f"=s{size}", f.thumbnail_link)
        resp = self.session.get(
            link, headers={"Authorization": f"Bearer {self.auth.token()}"}, stream=True, timeout=(10, 30)
        )
        if not resp.ok or not resp.headers.get("Content-Type", "").startswith("image/"):
            resp.close()
            return None
        return resp
