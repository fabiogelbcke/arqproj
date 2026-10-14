"""Connect an office's own Google Drive with OAuth, and keep reads working.

Two credentials, each doing what it is actually good at:

  OAuth (drive.file)
      Writes. Creates the delivery folder and the project/stage structure.
      Non-sensitive scope, so Google never requires verification or a security
      assessment. It can only ever see files this app itself created.

  Service account
      Reads. The delivery folder is shared with it at the moment it is created,
      so everything the architect drops in later is readable. A Drive share
      does not expire the way a refresh token does, which matters because the
      read path is what clients depend on.

Established by experiment (Oct 2026), not assumed:

  * `drive.file` does NOT grant access to files the *user* adds to a folder the
    *app* created. Listing such a folder returns only the app's own files.
  * The app CAN share an app-created folder with the service account -- but only
    while that folder holds nothing the app lacks access to. Once a foreign file
    is inside, the call fails with `appNotAuthorizedToChild`. Hence: share at
    creation time, before anything lands in it.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.parse
from dataclasses import dataclass

import requests

from .config import slugify
from .stages import STANDARD_STAGES
from .google_auth import GCS_SCOPE, get_auth

SCOPE = "https://www.googleapis.com/auth/drive.file"
AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
DRIVE_API = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD = "https://www.googleapis.com/upload/drive/v3"
FOLDER_MIME = "application/vnd.google-apps.folder"

# A project folder starts hidden (the app hides anything prefixed "_") so that
# nothing appears on the client-facing site until it is deliberately published.
DRAFT_PREFIX = "_"


class NotConnected(RuntimeError):
    """No usable OAuth credentials: never connected, or the grant was revoked."""


class DriveWriteError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(f"Drive API error {status}: {message}")
        self.status = status
        self.message = message


# ---------------------------------------------------------------------------
# configuration
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class OAuthConfig:
    client_id: str
    client_secret: str
    redirect_uri: str

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.redirect_uri)

    @classmethod
    def from_env(cls) -> "OAuthConfig":
        return cls(
            client_id=os.environ.get("OAUTH_CLIENT_ID", "").strip(),
            client_secret=os.environ.get("OAUTH_CLIENT_SECRET", "").strip(),
            redirect_uri=os.environ.get("OAUTH_REDIRECT_URI", "").strip(),
        )


def authorize_url(cfg: OAuthConfig, state: str) -> str:
    params = {
        "client_id": cfg.client_id,
        "redirect_uri": cfg.redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",   # we need a refresh token
        "prompt": "consent",        # ...and Google only resends one if we ask
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{os.environ.get('OAUTH_AUTH_URI') or AUTH_URI}?{urllib.parse.urlencode(params)}"


# ---------------------------------------------------------------------------
# where the refresh token lives
# ---------------------------------------------------------------------------
class FileStateStore:
    """Local development: a JSON file next to the code."""

    def __init__(self, path: str):
        self.path = path

    def load(self) -> dict:
        try:
            with open(self.path, encoding="utf-8") as fh:
                return json.load(fh)
        except FileNotFoundError:
            return {}

    def save(self, state: dict) -> None:
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2)
        os.chmod(self.path, 0o600)


class GcsStateStore:
    """Cloud Run: one small JSON object in a bucket.

    Cloud Run instances are ephemeral and there can be several, so the refresh
    token cannot live on local disk. It is written rarely -- only when someone
    connects or reconnects -- so a plain object is plenty.
    """

    def __init__(self, bucket: str, name: str = "drive-connection.json", session=None):
        self.bucket = bucket
        self.name = name
        self._session = session or requests
        self._auth = get_auth(GCS_SCOPE)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._auth.token()}"}

    def load(self) -> dict:
        url = (f"https://storage.googleapis.com/storage/v1/b/{self.bucket}"
               f"/o/{urllib.parse.quote(self.name, safe='')}")
        r = self._session.get(url, params={"alt": "media"}, headers=self._headers(), timeout=15)
        if r.status_code == 404:
            return {}
        if not r.ok:
            raise DriveWriteError(r.status_code, r.text[:300])
        return r.json()

    def save(self, state: dict) -> None:
        url = f"https://storage.googleapis.com/upload/storage/v1/b/{self.bucket}/o"
        r = self._session.post(
            url,
            params={"uploadType": "media", "name": self.name},
            headers={**self._headers(), "Content-Type": "application/json"},
            data=json.dumps(state).encode(),
            timeout=15,
        )
        if not r.ok:
            raise DriveWriteError(r.status_code, r.text[:300])


def default_state_store():
    bucket = os.environ.get("PORTAL_STATE_BUCKET", "").strip()
    if bucket:
        return GcsStateStore(bucket)
    return FileStateStore(os.environ.get("PORTAL_STATE_FILE", ".drive-connection.json"))


# ---------------------------------------------------------------------------
# the Drive write client
# ---------------------------------------------------------------------------
class DriveWriter:
    def __init__(self, token: str, session=None, base_url: str = DRIVE_API,
                 upload_url: str = DRIVE_UPLOAD):
        self.token = token
        self._session = session or requests
        self.base_url = base_url
        self.upload_url = upload_url

    def _call(self, method: str, path: str, *, base: str | None = None, **kw):
        headers = kw.pop("headers", {})
        headers["Authorization"] = f"Bearer {self.token}"
        params = kw.pop("params", {})
        params.setdefault("supportsAllDrives", "true")
        r = self._session.request(method, f"{base or self.base_url}{path}",
                                  headers=headers, params=params, timeout=30, **kw)
        if not r.ok:
            raise DriveWriteError(r.status_code, r.text[:400])
        return r.json() if r.content else {}

    def about(self) -> dict:
        return self._call("GET", "/about", params={"fields": "user,storageQuota"})

    def create_folder(self, name: str, parent: str | None = None,
                      app_properties: dict | None = None) -> dict:
        body: dict = {"name": name, "mimeType": FOLDER_MIME}
        if parent:
            body["parents"] = [parent]
        if app_properties:
            body["appProperties"] = app_properties
        return self._call("POST", "/files", json=body,
                          params={"fields": "id,name,webViewLink"})

    def share(self, file_id: str, email: str, role: str = "reader") -> dict:
        """Give the service account read access. Must happen before any file the
        app cannot see ends up inside, or Drive refuses with appNotAuthorizedToChild."""
        return self._call("POST", f"/files/{file_id}/permissions",
                          json={"role": role, "type": "user", "emailAddress": email},
                          params={"sendNotificationEmail": "false"})

    def list_children(self, folder_id: str) -> list[dict]:
        out = self._call("GET", "/files", params={
            "q": f"'{folder_id}' in parents and trashed=false",
            "fields": "files(id,name,mimeType,modifiedTime,appProperties)",
            "orderBy": "folder,name",
            "includeItemsFromAllDrives": "true",
        })
        return out.get("files", [])

    def rename(self, file_id: str, name: str) -> dict:
        return self._call("PATCH", f"/files/{file_id}", json={"name": name},
                          params={"fields": "id,name"})

    def create_text_file(self, name: str, parent: str, text: str) -> dict:
        """Two calls instead of a multipart/related body: upload the bytes, then
        set the name and parent. Less code, and much easier to get right."""
        created = self._call("POST", "/files", base=self.upload_url,
                             params={"uploadType": "media", "fields": "id"},
                             headers={"Content-Type": "text/plain; charset=utf-8"},
                             data=text.encode("utf-8"))
        return self._call("PATCH", f"/files/{created['id']}",
                          json={"name": name},
                          params={"addParents": parent, "fields": "id,name"})


# ---------------------------------------------------------------------------
# the connection: state + token refresh + the operations the panel needs
# ---------------------------------------------------------------------------
class Connection:
    def __init__(self, cfg: OAuthConfig, store=None, service_account_email: str = "",
                 session=None):
        self.cfg = cfg
        self.store = store or default_state_store()
        self.service_account_email = service_account_email
        self._session = session or requests
        # Overridable so local test mode can point at the fake Google in tools/fake_drive.py.
        self.token_uri = os.environ.get("OAUTH_TOKEN_URI") or TOKEN_URI
        self.api_base = os.environ.get("DRIVE_API_BASE") or DRIVE_API
        self.upload_base = self.api_base.replace("/drive/v3", "/upload/drive/v3")
        self._access: str | None = None
        self._expires_at = 0.0
        self._lock = threading.Lock()

    # -- state ------------------------------------------------------------
    def state(self) -> dict:
        return self.store.load()

    @property
    def connected(self) -> bool:
        return bool(self.state().get("refresh_token"))

    def disconnect(self) -> None:
        self.store.save({})
        with self._lock:
            self._access, self._expires_at = None, 0.0

    # -- tokens -----------------------------------------------------------
    def complete_login(self, code: str) -> dict:
        r = self._session.post(self.token_uri, data={
            "code": code,
            "client_id": self.cfg.client_id,
            "client_secret": self.cfg.client_secret,
            "redirect_uri": self.cfg.redirect_uri,
            "grant_type": "authorization_code",
        }, timeout=30)
        if not r.ok:
            raise DriveWriteError(r.status_code, r.text[:300])
        tok = r.json()
        if not tok.get("refresh_token"):
            # Without prompt=consent Google omits it on re-authorisation.
            raise DriveWriteError(400, "Google did not return a refresh token")
        state = self.state()
        state["refresh_token"] = tok["refresh_token"]
        self.store.save(state)
        with self._lock:
            self._access = tok["access_token"]
            self._expires_at = time.time() + int(tok.get("expires_in", 3600))
        return tok

    def access_token(self) -> str:
        with self._lock:
            if self._access and time.time() < self._expires_at - 60:
                return self._access
        refresh = self.state().get("refresh_token")
        if not refresh:
            raise NotConnected("no refresh token stored")
        r = self._session.post(self.token_uri, data={
            "client_id": self.cfg.client_id,
            "client_secret": self.cfg.client_secret,
            "refresh_token": refresh,
            "grant_type": "refresh_token",
        }, timeout=30)
        if r.status_code in (400, 401):
            # Revoked, expired, or the password was changed: make the panel say so
            # rather than failing somewhere deeper.
            raise NotConnected(f"refresh rejected ({r.status_code})")
        if not r.ok:
            raise DriveWriteError(r.status_code, r.text[:300])
        tok = r.json()
        with self._lock:
            self._access = tok["access_token"]
            self._expires_at = time.time() + int(tok.get("expires_in", 3600))
            return self._access

    def writer(self) -> DriveWriter:
        return DriveWriter(self.access_token(), session=self._session,
                           base_url=self.api_base, upload_url=self.upload_base)

    # -- operations -------------------------------------------------------
    def setup_delivery_folder(self, name: str) -> dict:
        """Create the folder and share it with the service account immediately.

        Order matters: the share is only permitted while the folder is empty of
        anything the app cannot see.
        """
        w = self.writer()
        folder = w.create_folder(name, app_properties={"portal": "delivery-root"})
        shared = False
        if self.service_account_email:
            w.share(folder["id"], self.service_account_email)
            shared = True
        state = self.state()
        state.update(delivery_folder_id=folder["id"], delivery_folder_name=folder["name"],
                     shared_with_service_account=shared)
        self.store.save(state)
        return folder

    def create_project(self, title: str, stages: list[str], slug: str = "") -> dict:
        """Create a draft project folder with its stages, plus a `_project` doc.

        Draft: the folder name is prefixed, so the existing reader hides it from
        clients until it is published.
        """
        state = self.state()
        root = state.get("delivery_folder_id")
        if not root:
            raise DriveWriteError(400, "no delivery folder yet")
        w = self.writer()
        # The link is also kept on the folder, so duplicates can be checked without
        # reading every draft's `_project` doc.
        project = w.create_folder(DRAFT_PREFIX + title, parent=root,
                                  app_properties={"portal": "project",
                                                  "slug": slug or slugify(title)})
        lines = [f"Title: {title}"]
        if slug:
            lines.append(f"Slug: {slug}")
        w.create_text_file("_project.txt", project["id"], "\n".join(lines) + "\n")
        for position, stage in enumerate(stages, start=1):
            w.create_folder(f"{position:02d} - {stage}", parent=project["id"],
                            app_properties={"portal": "stage", "position": str(position)})
        return project

    def publish_project(self, folder_id: str, title: str) -> dict:
        return self.writer().rename(folder_id, title.lstrip(DRAFT_PREFIX))

    def projects(self) -> list[dict]:
        state = self.state()
        root = state.get("delivery_folder_id")
        if not root:
            return []
        out = []
        for f in self.writer().list_children(root):
            if f.get("mimeType") != FOLDER_MIME:
                continue
            name = f["name"]
            title = name.lstrip(DRAFT_PREFIX)
            out.append({**f, "draft": name.startswith(DRAFT_PREFIX), "title": title,
                        "slug": (f.get("appProperties") or {}).get("slug") or slugify(title)})
        return out


# Editable defaults offered in the painel: the office's standard workflow, so new
# projects get the stage explanations shown on the client page.
DEFAULT_STAGES = list(STANDARD_STAGES)


def service_account_email(default: str = "") -> str:
    """The identity the delivery folder gets shared with.

    SERVICE_ACCOUNT_EMAIL wins; otherwise take it from the local key file, or
    ask the metadata server on Cloud Run.
    """
    explicit = os.environ.get("SERVICE_ACCOUNT_EMAIL", "").strip()
    if explicit:
        return explicit
    try:
        email = getattr(get_auth(), "email", "")
        if email:
            return email
    except Exception:
        pass
    if os.environ.get("K_SERVICE"):
        try:
            r = requests.get(
                "http://metadata.google.internal/computeMetadata/v1/instance"
                "/service-accounts/default/email",
                headers={"Metadata-Flavor": "Google"}, timeout=5)
            if r.ok:
                return r.text.strip()
        except requests.RequestException:
            pass
    return default
