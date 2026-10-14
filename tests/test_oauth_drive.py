"""Unit tests for the OAuth Drive connection, against a fake HTTP session.

The invariants worth protecting are the two the experiments revealed:
  * the delivery folder is shared with the service account at creation time,
    while it is still empty (otherwise Drive refuses with appNotAuthorizedToChild);
  * a rejected refresh surfaces as NotConnected, so the panel can say "reconnect"
    instead of failing somewhere deeper.

    python -m unittest discover -s tests -v
"""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arq import oauth_drive  # noqa: E402


class FakeResponse:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = {} if payload is None else payload
        self.text = json.dumps(self._payload)
        self.content = self.text.encode()

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        return self._payload


class FakeSession:
    """Just enough of requests to drive the module."""

    def __init__(self, token_responses=None):
        self.calls = []
        self.token_responses = list(token_responses or [])
        self.children = []
        self._n = 0

    # Connection uses .post for the token endpoint
    def post(self, url, data=None, timeout=None, **kw):
        self.calls.append(("POST", url, data))
        assert url == oauth_drive.TOKEN_URI, url
        return self.token_responses.pop(0)

    # DriveWriter uses .request for everything
    def request(self, method, url, headers=None, params=None, json=None, data=None, timeout=None):
        self.calls.append((method, url, {"params": params, "json": json, "data": data}))
        if url.endswith("/about"):
            return FakeResponse(200, {"user": {"emailAddress": "arq@example.com"},
                                      "storageQuota": {"limit": "1000", "usage": "900"}})
        if method == "POST" and url.endswith("/permissions"):
            return FakeResponse(200, {"id": "perm1", "role": "reader"})
        if method == "POST" and url.startswith(oauth_drive.DRIVE_UPLOAD):
            self._n += 1
            return FakeResponse(200, {"id": f"upload{self._n}"})
        if method == "POST" and url.endswith("/files"):
            self._n += 1
            return FakeResponse(200, {"id": f"folder{self._n}", "name": json["name"]})
        if method == "PATCH":
            return FakeResponse(200, {"id": url.rsplit("/", 1)[-1],
                                      "name": (json or {}).get("name")})
        if method == "GET" and url.endswith("/files"):
            return FakeResponse(200, {"files": self.children})
        raise AssertionError(f"unexpected {method} {url}")

    def drive_calls(self):
        return [(m, u, kw) for m, u, kw in self.calls if u != oauth_drive.TOKEN_URI]


def token_ok(access="at-1", refresh="rt-1"):
    body = {"access_token": access, "expires_in": 3600}
    if refresh:
        body["refresh_token"] = refresh
    return FakeResponse(200, body)


class Base(unittest.TestCase):
    def setUp(self):
        # Other test modules point DRIVE_API_BASE at a fake server; these tests
        # check the real Google endpoints.
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        for key in ("DRIVE_API_BASE", "OAUTH_TOKEN_URI", "OAUTH_AUTH_URI"):
            os.environ.pop(key, None)
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.close()
        os.unlink(self.tmp.name)
        self.store = oauth_drive.FileStateStore(self.tmp.name)
        self.cfg = oauth_drive.OAuthConfig("cid", "csec", "https://example.com/cb")

    def tearDown(self):
        if os.path.exists(self.tmp.name):
            os.unlink(self.tmp.name)

    def connection(self, session):
        return oauth_drive.Connection(self.cfg, store=self.store,
                                      service_account_email="sa@proj.iam.gserviceaccount.com",
                                      session=session)


class AuthorizeUrl(unittest.TestCase):
    @mock.patch.dict(os.environ, {"OAUTH_AUTH_URI": ""})
    def test_asks_for_drive_file_and_a_refresh_token(self):
        cfg = oauth_drive.OAuthConfig("cid", "csec", "https://example.com/cb")
        url = oauth_drive.authorize_url(cfg, "st8")
        self.assertIn("scope=https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fdrive.file", url)
        self.assertIn("access_type=offline", url)   # otherwise no refresh token
        self.assertIn("prompt=consent", url)        # ...and none on re-auth either
        self.assertIn("state=st8", url)

    def test_configured_requires_all_three(self):
        self.assertFalse(oauth_drive.OAuthConfig("", "b", "c").configured)
        self.assertTrue(oauth_drive.OAuthConfig("a", "b", "c").configured)


class Tokens(Base):
    def test_login_stores_refresh_token(self):
        s = FakeSession([token_ok()])
        conn = self.connection(s)
        conn.complete_login("code-123")
        self.assertEqual(self.store.load()["refresh_token"], "rt-1")
        self.assertTrue(conn.connected)

    def test_login_without_refresh_token_is_an_error(self):
        s = FakeSession([token_ok(refresh=None)])
        with self.assertRaises(oauth_drive.DriveWriteError):
            self.connection(s).complete_login("code-123")

    def test_access_token_is_cached_after_login(self):
        s = FakeSession([token_ok()])
        conn = self.connection(s)
        conn.complete_login("code-123")
        self.assertEqual(conn.access_token(), "at-1")
        self.assertEqual(len(s.calls), 1)  # no second round trip

    def test_revoked_grant_raises_not_connected(self):
        s = FakeSession([token_ok(), FakeResponse(400, {"error": "invalid_grant"})])
        conn = self.connection(s)
        conn.complete_login("code-123")
        conn._access, conn._expires_at = None, 0  # force a refresh
        with self.assertRaises(oauth_drive.NotConnected):
            conn.access_token()

    def test_disconnect_clears_state(self):
        s = FakeSession([token_ok()])
        conn = self.connection(s)
        conn.complete_login("code-123")
        conn.disconnect()
        self.assertFalse(conn.connected)


class DeliveryFolder(Base):
    def test_share_happens_at_creation_while_empty(self):
        s = FakeSession([token_ok()])
        conn = self.connection(s)
        conn.complete_login("c")
        conn.setup_delivery_folder("Portal Clientes")

        calls = s.drive_calls()
        created = [c for c in calls if c[0] == "POST" and c[1].endswith("/files")]
        shared = [c for c in calls if c[1].endswith("/permissions")]
        self.assertEqual(len(created), 1)
        self.assertEqual(len(shared), 1)
        # The share must come straight after creation, before anything is added.
        self.assertLess(calls.index(created[0]), calls.index(shared[0]))
        self.assertEqual(shared[0][2]["json"]["emailAddress"], "sa@proj.iam.gserviceaccount.com")
        self.assertEqual(shared[0][2]["json"]["role"], "reader")

        state = self.store.load()
        self.assertEqual(state["delivery_folder_id"], "folder1")
        self.assertTrue(state["shared_with_service_account"])

    def test_no_share_when_no_service_account_configured(self):
        s = FakeSession([token_ok()])
        conn = oauth_drive.Connection(self.cfg, store=self.store, service_account_email="",
                                      session=s)
        conn.complete_login("c")
        conn.setup_delivery_folder("X")
        self.assertFalse(any(c[1].endswith("/permissions") for c in s.drive_calls()))
        self.assertFalse(self.store.load()["shared_with_service_account"])


class Projects(Base):
    def connected(self, session):
        conn = self.connection(session)
        conn.complete_login("c")
        conn.setup_delivery_folder("Portal")
        return conn

    def test_create_project_is_a_draft_with_numbered_stages(self):
        s = FakeSession([token_ok()])
        conn = self.connected(s)
        s.calls.clear()
        conn.create_project("Casa Jardim", ["Estudo", "Obra"], slug="casa-jardim")

        names = [c[2]["json"]["name"] for c in s.drive_calls()
                 if c[0] == "POST" and c[1].endswith("/files") and c[2]["json"]]
        self.assertEqual(names[0], "_Casa Jardim")  # hidden from clients until published
        self.assertEqual(names[1:], ["01 - Estudo", "02 - Obra"])

        uploaded = [c for c in s.drive_calls() if c[1].startswith(oauth_drive.DRIVE_UPLOAD)]
        self.assertEqual(len(uploaded), 1)
        body = uploaded[0][2]["data"].decode()
        self.assertIn("Title: Casa Jardim", body)
        self.assertIn("Slug: casa-jardim", body)

    def test_create_project_without_delivery_folder_fails_clearly(self):
        s = FakeSession([token_ok()])
        conn = self.connection(s)
        conn.complete_login("c")
        with self.assertRaises(oauth_drive.DriveWriteError):
            conn.create_project("X", ["A"])

    def test_publish_removes_the_draft_prefix(self):
        s = FakeSession([token_ok()])
        conn = self.connected(s)
        s.calls.clear()
        conn.publish_project("folder9", "_Casa Jardim")
        patch = [c for c in s.drive_calls() if c[0] == "PATCH"][0]
        self.assertEqual(patch[2]["json"]["name"], "Casa Jardim")

    def test_projects_flags_drafts_and_ignores_files(self):
        s = FakeSession([token_ok()])
        conn = self.connected(s)
        s.children = [
            {"id": "a", "name": "_Casa Jardim", "mimeType": oauth_drive.FOLDER_MIME},
            {"id": "b", "name": "Loja Centro", "mimeType": oauth_drive.FOLDER_MIME},
            {"id": "c", "name": "notes.txt", "mimeType": "text/plain"},
        ]
        got = conn.projects()
        self.assertEqual([(p["title"], p["draft"]) for p in got],
                         [("Casa Jardim", True), ("Loja Centro", False)])


class StateStore(unittest.TestCase):
    def test_file_store_round_trip_and_missing_file(self):
        with tempfile.TemporaryDirectory() as d:
            store = oauth_drive.FileStateStore(os.path.join(d, "s.json"))
            self.assertEqual(store.load(), {})
            store.save({"refresh_token": "x"})
            self.assertEqual(store.load()["refresh_token"], "x")


if __name__ == "__main__":
    unittest.main()
