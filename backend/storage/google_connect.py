"""Connecting an office's Google Drive: the sign-in, and the office's own grant.

The office signs in with Google and allows `drive.file` (only files this app
creates or opens; plan A04). With that grant the app creates the office's root
folder and, **while it is still empty**, shares it with the reader identity that
serves pages and downloads (plan section 9: once anything the app did not create
is inside, sharing fails). Google's error text is logged, never shown.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlencode

import httpx2

log = logging.getLogger(__name__)

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
DRIVE = "https://www.googleapis.com/drive/v3"
SCOPE = "https://www.googleapis.com/auth/drive.file"
FOLDER = "application/vnd.google-apps.folder"
ROOT_FOLDER_NAME = "Portal Clientes"


class ConnectProblem(StrEnum):
    EXCHANGE_FAILED = "exchange_failed"  # Google refused the sign-in code
    NO_REFRESH_TOKEN = "no_refresh_token"  # nothing to keep: cannot work offline
    FOLDER_FAILED = "folder_failed"
    SHARE_FAILED = "share_failed"
    OTHER_ACCOUNT = "other_account"  # this grant cannot reach the office's existing folder
    EXPIRED = "expired"  # the stored grant was revoked or expired


class ConnectError(Exception):
    def __init__(self, problem: ConnectProblem, detail: str = "") -> None:
        super().__init__(problem.value)
        self.problem = problem
        self.detail = detail  # for the server log only


@dataclass(frozen=True)
class OAuthClient:
    client_id: str
    client_secret: str
    redirect_uri: str

    def authorization_url(self, state: str) -> str:
        return f"{AUTH_URL}?" + urlencode(
            {
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "response_type": "code",
                "scope": SCOPE,
                "access_type": "offline",  # a refresh token, for work while nobody is signed in
                "prompt": "consent",  # always issue one, even on reconnect
                "include_granted_scopes": "true",
                "state": state,
            }
        )

    async def exchange(self, http: httpx2.AsyncClient, code: str) -> tuple[str, str]:
        """The sign-in code → (refresh token, access token)."""
        body = await self._token(
            http,
            {"code": code, "grant_type": "authorization_code", "redirect_uri": self.redirect_uri},
            ConnectProblem.EXCHANGE_FAILED,
        )
        if not body.get("refresh_token"):
            raise ConnectError(ConnectProblem.NO_REFRESH_TOKEN)
        return body["refresh_token"], body["access_token"]

    async def access_token(self, http: httpx2.AsyncClient, refresh_token: str) -> str:
        body = await self._token(
            http,
            {"refresh_token": refresh_token, "grant_type": "refresh_token"},
            ConnectProblem.EXPIRED,
        )
        return body["access_token"]

    async def revoke(self, http: httpx2.AsyncClient, refresh_token: str) -> None:
        """Best effort: the app forgets the grant either way."""
        try:
            response = await http.post(REVOKE_URL, data={"token": refresh_token})
            if response.status_code >= 400:
                log.warning("Google revoke answered %s", response.status_code)
        except httpx2.TransportError as error:
            log.warning("Google revoke failed: %r", error)

    async def _token(self, http, data: dict, problem: ConnectProblem) -> dict:
        data = data | {"client_id": self.client_id, "client_secret": self.client_secret}
        try:
            response = await http.post(TOKEN_URL, data=data)
        except httpx2.TransportError as error:
            raise ConnectError(problem, repr(error)) from error
        if response.status_code >= 400:
            # Never log the request: it holds the code or refresh token.
            raise ConnectError(problem, f"{response.status_code}: {response.text[:300]}")
        return response.json()


class DriveWriter:
    """Drive as the office's own grant (drive.file). A failed call, whether Google
    answered with an error or the network failed, is a `ConnectError`."""

    def __init__(self, http: httpx2.AsyncClient, access_token: str) -> None:
        self._http = http
        self._headers = {"Authorization": f"Bearer {access_token}"}

    async def _call(self, method: str, url: str, problem: ConnectProblem, **kwargs):
        try:
            response = await self._http.request(method, url, headers=self._headers, **kwargs)
        except httpx2.TransportError as error:
            raise ConnectError(problem, f"{url}: {error!r}") from error
        if response.status_code >= 400:
            raise ConnectError(problem, f"{response.status_code} {url}: {response.text[:300]}")
        return response

    async def account_email(self) -> str | None:
        try:
            response = await self._call(
                "GET",
                f"{DRIVE}/about",
                ConnectProblem.FOLDER_FAILED,
                params={"fields": "user(emailAddress)"},
            )
        except ConnectError as error:
            log.warning("Drive account unknown: %s", error.detail)
            return None
        return response.json().get("user", {}).get("emailAddress")

    async def can_open(self, folder_id: str) -> bool:
        """Whether this grant reaches a folder the app created before: False when
        Google says it cannot (another account, deleted, trashed). A failure that
        says nothing about access (network, Google's 5xx) raises `ConnectError`."""
        try:
            response = await self._http.get(
                f"{DRIVE}/files/{folder_id}",
                params={"fields": "id,trashed", "supportsAllDrives": "true"},
                headers=self._headers,
            )
        except httpx2.TransportError as error:
            raise ConnectError(ConnectProblem.FOLDER_FAILED, repr(error)) from error
        if response.status_code in (403, 404):
            return False
        if response.status_code >= 400:
            raise ConnectError(
                ConnectProblem.FOLDER_FAILED, f"{response.status_code}: {response.text[:300]}"
            )
        return not response.json().get("trashed")

    async def create_folder(self, name: str, parent: str | None = None) -> str:
        metadata = {"name": name, "mimeType": FOLDER} | ({"parents": [parent]} if parent else {})
        response = await self._call(
            "POST",
            f"{DRIVE}/files",
            ConnectProblem.FOLDER_FAILED,
            params={"fields": "id", "supportsAllDrives": "true"},
            json=metadata,
        )
        return response.json()["id"]

    async def share_with_reader(self, folder_id: str, reader: str) -> None:
        await self._call(
            "POST",
            f"{DRIVE}/files/{folder_id}/permissions",
            ConnectProblem.SHARE_FAILED,
            params={"sendNotificationEmail": "false", "supportsAllDrives": "true"},
            json={"type": "user", "role": "reader", "emailAddress": reader},
        )

    async def trash(self, item_id: str) -> None:
        try:
            await self._call(
                "PATCH",
                f"{DRIVE}/files/{item_id}",
                ConnectProblem.FOLDER_FAILED,
                params={"supportsAllDrives": "true"},
                json={"trashed": True},
            )
        except ConnectError as error:
            log.warning("could not trash %s: %s", item_id, error.detail)
