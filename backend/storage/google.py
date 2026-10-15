"""Google Drive, read as the server's own Google identity.

No key files: on Cloud Run the identity is the service's account (staging:
`portal-staging@`); on a laptop, application default credentials. Each office's
folder is shared with that identity for reading (plan section 9). Writes go
through the office's own OAuth grant, in slice 3.

Google's error text is logged, never returned: callers get a `StorageProblem`.
Throttling and server errors are retried with growing waits before giving up.
"""

from __future__ import annotations

import logging
import random
import re
from collections.abc import Awaitable, Callable
from datetime import datetime

import anyio
import httpx2

from backend.storage.base import (
    Download,
    StorageError,
    StorageItem,
    StorageProblem,
    sorted_items,
)

log = logging.getLogger(__name__)

API = "https://www.googleapis.com/drive/v3"
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
FIELDS = "id,name,mimeType,size,modifiedTime,md5Checksum,trashed,shortcutDetails(targetId)"
# Drive ids are letters, digits, `-` and `_`. Anything else is refused before it
# can reach the `q` search expression.
_ID = re.compile(r"^[A-Za-z0-9_-]{1,200}$")
_THROTTLED = {"rateLimitExceeded", "userRateLimitExceeded"}
RETRIES = 3

TokenSource = Callable[[], Awaitable[str]]


class ServerIdentity:
    """Access tokens for the server's own Google identity, refreshed when due."""

    def __init__(self) -> None:
        self._credentials = None
        self._lock = anyio.Lock()

    async def __call__(self) -> str:
        async with self._lock:
            if self._credentials is None or not self._credentials.valid:
                await anyio.to_thread.run_sync(self._refresh)
            return self._credentials.token

    def _refresh(self) -> None:
        import google.auth
        from google.auth.transport.requests import Request

        if self._credentials is None:
            self._credentials, _ = google.auth.default(scopes=SCOPES)
        self._credentials.refresh(Request())


class GoogleDriveStorage:
    def __init__(
        self,
        token: TokenSource,
        client: httpx2.AsyncClient,
        *,
        api: str = API,
        sleep: Callable[[float], Awaitable[None]] = anyio.sleep,
    ) -> None:
        self._token = token
        self._client = client
        self._api = api
        self._sleep = sleep

    async def list_folder(self, folder_id: str) -> list[StorageItem]:
        # Drive's "in parents" search answers a deleted, trashed or unshared folder
        # with an empty list; check the folder itself so a broken binding is "not
        # found", not an empty stage (plan section 8).
        if not (await self.get(folder_id)).is_folder:
            raise StorageError(StorageProblem.NOT_FOUND)
        items, page = [], None
        while True:
            params = {
                "q": f"'{folder_id}' in parents and trashed = false",
                "fields": f"nextPageToken,files({FIELDS})",
                "pageSize": "1000",
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
            }
            if page:
                params["pageToken"] = page
            body = (await self._send("GET", f"{self._api}/files", params)).json()
            items += [_item(f) for f in body.get("files", [])]
            page = body.get("nextPageToken")
            if not page:
                return sorted_items(items)

    async def get(self, item_id: str) -> StorageItem:
        _check(item_id)
        body = (
            await self._send(
                "GET",
                f"{self._api}/files/{item_id}",
                {"fields": FIELDS, "supportsAllDrives": "true"},
            )
        ).json()
        if body.get("trashed"):
            raise StorageError(StorageProblem.NOT_FOUND)
        return _item(body)

    async def download(self, item: StorageItem) -> Download:
        _check(item.id)
        if item.is_folder or item.is_shortcut or (item.is_native and not item.exports_as_pdf):
            raise StorageError(StorageProblem.NOT_FOUND)
        if item.is_native:
            url, params = f"{self._api}/files/{item.id}/export", {"mimeType": "application/pdf"}
            media_type, size = "application/pdf", None
        else:
            url = f"{self._api}/files/{item.id}"
            params = {"alt": "media", "supportsAllDrives": "true"}
            media_type, size = item.mime_type, item.size
        response = await self._send("GET", url, params, stream=True)

        async def chunks():
            try:
                async for block in response.aiter_bytes():
                    yield block
            except httpx2.TransportError as error:  # the connection dropped mid-file
                raise StorageError(StorageProblem.UNAVAILABLE, f"{url}: {error!r}") from error
            finally:
                await response.aclose()

        return Download(media_type, size, chunks(), aclose=response.aclose)

    async def thumbnail(self, item: StorageItem, size: int = 640) -> bytes | None:
        _check(item.id)
        body = (
            await self._send(
                "GET",
                f"{self._api}/files/{item.id}",
                {"fields": "thumbnailLink", "supportsAllDrives": "true"},
            )
        ).json()
        link = body.get("thumbnailLink")
        if not link:
            return None
        # Google's links end in "=s220"; ask for the size we want instead.
        return (await self._send("GET", re.sub(r"=s\d+$", f"=s{size}", link), {})).content

    async def _send(
        self, method: str, url: str, params: dict, *, stream: bool = False
    ) -> httpx2.Response:
        problem, detail = StorageProblem.UNAVAILABLE, ""
        for attempt in range(RETRIES + 1):
            if attempt:
                await self._sleep(0.5 * 2**attempt + random.random() / 2)
            try:
                token = await self._token()
            except Exception as error:  # e.g. no credentials, or Google's token service down
                problem, detail = StorageProblem.UNAVAILABLE, f"token: {error!r}"
                log.warning("Drive token unavailable: %r", error)
                continue
            headers = {"Authorization": f"Bearer {token}"}
            request = self._client.build_request(method, url, params=params, headers=headers)
            try:
                response = await self._client.send(request, stream=stream)
            except httpx2.TransportError as error:
                problem, detail = StorageProblem.UNAVAILABLE, f"{url}: {error!r}"
                log.warning("Drive request failed (%s): %s", url, error)
                continue
            if response.status_code < 400:
                return response
            if stream:
                await response.aread()
            problem, retry = _classify(response)
            detail = f"{response.status_code} {url}: {response.text[:500]}"
            log.warning("Drive answered %s", detail)
            await response.aclose()
            if not retry:
                break
        raise StorageError(problem, detail)

    async def parent(self, item_id: str) -> str | None:
        """The folder an item is in (Drive items have one), or None at the top."""
        _check(item_id)
        body = (
            await self._send(
                "GET",
                f"{self._api}/files/{item_id}",
                {"fields": "parents,trashed", "supportsAllDrives": "true"},
            )
        ).json()
        if body.get("trashed"):
            raise StorageError(StorageProblem.NOT_FOUND)
        parents = body.get("parents") or []
        return parents[0] if parents else None


# Deeper than any real project tree; stops a walk that never reaches a root.
MAX_DEPTH = 25


class OfficeDrive:
    """Google Drive limited to one office's root folder and what is inside it.

    The reader identity may see several offices' folders (one shared reader, plan
    section 9), so an id alone proves nothing: before reading, the item's parent
    chain must reach this office's root. Confirmed folders are remembered for the
    life of this object (one request), and items listed inside a confirmed folder
    are confirmed with it.
    """

    def __init__(self, drive: GoogleDriveStorage, root_id: str) -> None:
        _check(root_id)
        self._drive = drive
        self._root = root_id
        self._inside = {root_id}

    async def _require_inside(self, item_id: str) -> None:
        _check(item_id)
        chain, current = [], item_id
        for _ in range(MAX_DEPTH):
            if current in self._inside:
                self._inside.update(chain)
                return
            chain.append(current)
            current = await self._drive.parent(current)
            if current is None:
                break
        log.warning("Drive item %s is outside office root %s", item_id, self._root)
        raise StorageError(StorageProblem.NOT_FOUND, f"{item_id} outside root {self._root}")

    async def list_folder(self, folder_id: str) -> list[StorageItem]:
        await self._require_inside(folder_id)
        children = await self._drive.list_folder(folder_id)
        self._inside.update(child.id for child in children)
        return children

    async def get(self, item_id: str) -> StorageItem:
        await self._require_inside(item_id)
        return await self._drive.get(item_id)

    async def download(self, item: StorageItem) -> Download:
        await self._require_inside(item.id)
        return await self._drive.download(item)

    async def thumbnail(self, item: StorageItem, size: int = 640) -> bytes | None:
        await self._require_inside(item.id)
        return await self._drive.thumbnail(item, size)


def _classify(response: httpx2.Response) -> tuple[StorageProblem, bool]:
    """The problem, and whether waiting and trying again may help."""
    status = response.status_code
    if status == 404:
        return StorageProblem.NOT_FOUND, False
    if status == 429:
        return StorageProblem.RATE_LIMITED, True
    if status >= 500:
        return StorageProblem.UNAVAILABLE, True
    try:
        reasons = {e.get("reason") for e in response.json()["error"].get("errors", [])}
    except (ValueError, KeyError, TypeError, AttributeError):
        reasons = set()
    if reasons & _THROTTLED:
        return StorageProblem.RATE_LIMITED, True
    return StorageProblem.NO_ACCESS, False


def _check(item_id: str) -> None:
    if not _ID.match(item_id):
        raise StorageError(StorageProblem.NOT_FOUND)


def _item(data: dict) -> StorageItem:
    return StorageItem(
        id=data["id"],
        name=data["name"],
        mime_type=data["mimeType"],
        size=int(data["size"]) if data.get("size") is not None else None,
        modified_at=datetime.fromisoformat(data["modifiedTime"].replace("Z", "+00:00")),
        checksum=data.get("md5Checksum"),
        shortcut_target=(data.get("shortcutDetails") or {}).get("targetId"),
    )
