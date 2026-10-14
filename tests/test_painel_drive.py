"""The painel's Drive modals and office settings, end to end against the fake Google.

Connect -> consent -> callback creates the projects folder -> new project -> publish,
plus the office name/logo settings, all over real HTTP to tools/fake_drive.py.

    python -m unittest discover -s tests -v
"""

import os
import re
import sys
import tempfile
import threading
import unittest
from io import BytesIO
from unittest import mock
from urllib.parse import parse_qs, urlparse

from werkzeug.serving import make_server

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arq import site_settings  # noqa: E402
from arq.oauth_drive import FileStateStore  # noqa: E402
from tools.fake_drive import (FOLDER, OAUTH_ACCOUNT, OAUTH_CODE, OAUTH_TOKEN,  # noqa: E402
                              FakeDrive, service_account_json)

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 32
PASSWORD = "painel test"


class PainelBase(unittest.TestCase):
    """Fake Google over real HTTP, a fresh app and a logged-in painel per test."""

    @classmethod
    def setUpClass(cls):
        cls.fake = FakeDrive("http://127.0.0.1:0", example_language="en")
        cls.server = make_server("127.0.0.1", 0, cls.fake.app(), threaded=True)
        cls.fake.base_url = f"http://127.0.0.1:{cls.server.server_port}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.addClassCleanup(cls.server.server_close)
        cls.addClassCleanup(cls.server.shutdown)

    def setUp(self):
        state_dir = tempfile.mkdtemp(prefix="arq-painel-")
        self.state_file = os.path.join(state_dir, "drive.json")
        env = mock.patch.dict(os.environ, {
            "GOOGLE_SERVICE_ACCOUNT_KEY": service_account_json(self.fake),
            "DRIVE_API_BASE": f"{self.fake.base_url}/drive/v3",
            "DRIVE_ROOT_FOLDER_ID": self.fake.root_id,
            "DASHBOARD_PASSWORD": PASSWORD,
            "SITE_LANG": "en",
            "SITE_NAME": "Test Office",
            "OAUTH_CLIENT_ID": "cid",
            "OAUTH_CLIENT_SECRET": "csec",
            "OAUTH_REDIRECT_URI": "http://localhost/painel/drive/callback",
            "OAUTH_AUTH_URI": f"{self.fake.base_url}/o/oauth2/v2/auth",
            "OAUTH_TOKEN_URI": f"{self.fake.base_url}/token",
            "PORTAL_STATE_FILE": self.state_file,
            "PORTAL_SETTINGS_FILE": os.path.join(state_dir, "settings.json"),
        })
        env.start()
        self.addCleanup(env.stop)
        for key in ("PORTAL_STATE_BUCKET", "SERVICE_ACCOUNT_EMAIL"):
            os.environ.pop(key, None)
        from app import create_app

        self.client = create_app().test_client()
        self.assertEqual(self.client.post("/painel/login", data={"password": PASSWORD}).status_code, 302)

    # -- helpers -----------------------------------------------------------
    def painel(self) -> str:
        r = self.client.get("/painel")
        self.assertEqual(r.status_code, 200)
        return r.get_data(as_text=True)

    def start_connect(self, folder_name="Client Portal") -> str:
        r = self.client.post("/painel/drive/connect", data={"folder_name": folder_name})
        self.assertEqual(r.status_code, 302)
        target = urlparse(r.location)
        self.assertEqual(f"{target.scheme}://{target.netloc}{target.path}",
                         f"{self.fake.base_url}/o/oauth2/v2/auth")
        return parse_qs(target.query)["state"][0]

    def connect(self, folder_name="Client Portal"):
        state = self.start_connect(folder_name)
        r = self.client.get("/painel/drive/callback", query_string={"code": OAUTH_CODE, "state": state})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.location.endswith("/painel"))

    def node(self, name):
        # The fake Drive is shared by the class, so take the most recent match.
        return next(n for n in reversed(list(self.fake.nodes.values())) if n.name == name)



class PainelDrive(PainelBase):
    # -- connecting --------------------------------------------------------
    def test_not_connected_offers_the_connect_modal_with_a_default_folder_name(self):
        html = self.painel()
        self.assertIn('data-open-dialog="connect-dialog"', html)
        self.assertIn('id="connect-dialog"', html)
        self.assertIn('name="folder_name" value="Portal Clientes"', html)
        self.assertNotIn('id="project-dialog"', html)
        self.assertNotIn('id="folder-dialog"', html)

    def test_the_old_drive_page_redirects_to_the_painel(self):
        r = self.client.get("/painel/drive")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.location.endswith("/painel"))

    def test_connecting_creates_the_named_folder_and_shares_it(self):
        self.connect("Client Portal")
        folder = self.node("Client Portal")
        self.assertEqual(folder.mime, FOLDER)
        self.assertTrue(folder.app_created)
        state = FileStateStore(self.state_file).load()
        self.assertEqual(state["delivery_folder_id"], folder.id)
        self.assertTrue(state["shared_with_service_account"])

        html = self.painel()
        self.assertIn("Google Drive connected. We created the folder “Client Portal”.", html)
        self.assertEqual(html.count('class="flash'), 1)  # one message, not two
        self.assertIn('data-open-dialog="project-dialog"', html)
        self.assertIn('id="project-dialog"', html)
        self.assertNotIn('id="connect-dialog"', html)
        self.assertNotIn('id="folder-dialog"', html)
        self.assertIn(OAUTH_ACCOUNT, html)  # in the settings modal
        self.assertNotIn("gserviceaccount.com", html)  # system details stay out of the UI
        self.assertIn('id="disconnect-dialog"', html)  # disconnecting asks first

    def test_failed_folder_creation_shows_the_required_folder_modal(self):
        with mock.patch("arq.oauth_drive.Connection.setup_delivery_folder",
                        side_effect=RuntimeError("Drive API error 500: secret detail")):
            self.connect()
        html = self.painel()
        self.assertRegex(html, r'id="folder-dialog"[^>]*data-required[^>]*data-open-on-load')
        self.assertNotIn("secret detail", html)
        self.assertNotIn('id="project-dialog"', html)

        r = self.client.post("/painel/drive/setup", data={"name": "Second Try"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.node("Second Try").mime, FOLDER)
        self.assertNotIn('id="folder-dialog"', self.painel())

    def test_setup_never_creates_a_second_folder(self):
        self.connect("Client Portal")
        before = len(self.fake.nodes)
        self.client.post("/painel/drive/setup", data={"name": "Another"})
        self.assertEqual(len(self.fake.nodes), before)

    def test_cancelled_consent(self):
        state = self.start_connect()
        self.client.get("/painel/drive/callback", query_string={"error": "access_denied", "state": state})
        self.assertIn("Authorisation was cancelled.", self.painel())
        self.assertFalse(FileStateStore(self.state_file).load())

    def test_rejected_login_shows_a_code_not_the_upstream_error(self):
        state = self.start_connect()
        with self.assertLogs("app", level="ERROR") as logs:
            self.client.get("/painel/drive/callback", query_string={"code": "wrong", "state": state})
        html = self.painel()
        ref = re.search(r"send us this code: ([0-9a-f]{6})", html)
        self.assertIsNotNone(ref)
        self.assertIn(ref.group(1), "\n".join(logs.output))  # the log line carries the same code
        message = html.split('class="flash flash--error" role="alert">', 1)[1].split("</p>", 1)[0]
        for leak in ("invalid_grant", "Drive API error", "400"):
            self.assertNotIn(leak, message)

    def test_callback_rejects_a_forged_state(self):
        self.start_connect()
        self.client.get("/painel/drive/callback", query_string={"code": OAUTH_CODE, "state": "forged"})
        self.assertIn("That sign-in attempt expired.", self.painel())
        self.assertFalse(FileStateStore(self.state_file).load())

    # -- projects ----------------------------------------------------------
    def test_new_project_is_a_draft_with_the_chosen_stages_and_can_be_published(self):
        self.connect()
        r = self.client.post("/painel/drive/project", data={
            "title": "Casa Lago", "slug": "casa-lago",
            "stage": ["Estudo", "", "Obra"],  # blank rows from the editor are dropped
        })
        self.assertEqual(r.status_code, 302)
        draft = self.node("_Casa Lago")
        self.assertEqual(sorted(c.name for c in draft.children), ["01 Estudo", "02 Obra", "_project.txt"])
        config = next(c for c in draft.children if c.name == "_project.txt")
        self.assertIn("Slug: casa-lago", config.text)

        html = self.painel()
        self.assertIn("Created “Casa Lago” as a draft.", html)
        self.assertRegex(html, r'drive-projects__title">Casa Lago</span>\s*<span class="pill pill--hidden">Draft')

        self.client.post("/painel/drive/publish", data={"folder_id": draft.id, "title": "Casa Lago"})
        self.assertEqual(draft.name, "Casa Lago")
        self.assertIn("Published.", self.painel())

    def create(self, **data):
        data.setdefault("stage", ["Obra"])
        return self.client.post("/painel/drive/project", data=data)

    def test_duplicate_names_are_refused_including_drafts_and_case(self):
        self.connect()
        self.assertEqual(self.create(title="Casa Lago").status_code, 302)
        before = len(self.fake.nodes)
        r = self.create(title="casa lago", slug="another-link")
        html = r.get_data(as_text=True)
        self.assertEqual(r.status_code, 400)
        self.assertIn("There is already a project called “Casa Lago”.", html)
        self.assertRegex(html, r'id="project-dialog"[^>]*data-open-on-load')
        self.assertIn('value="casa lago"', html)       # what was typed is kept
        self.assertIn('value="another-link"', html)
        self.assertEqual(len(self.fake.nodes), before)  # nothing created

    def test_duplicate_links_are_refused(self):
        self.connect()
        self.create(title="Casa Lago")
        # Same link as the draft, reached through a different name.
        r = self.create(title="Casa-Lago!")
        self.assertEqual(r.status_code, 400)
        self.assertIn("The link /casa-lago is already used by “Casa Lago”.", r.get_data(as_text=True))
        # Same link as a project already on the site.
        r = self.create(title="Casa Inédita", slug="casa-jardim")
        self.assertEqual(r.status_code, 400)
        self.assertIn("The link /casa-jardim is already used by", r.get_data(as_text=True))

    def test_link_is_normalised_and_kept_on_the_folder(self):
        self.connect()
        self.create(title="Casa Árvore", slug="Casa Árvore 2")
        folder = self.node("_Casa Árvore")
        self.assertEqual(folder.app_properties["slug"], "casa-arvore-2")
        config = next(c for c in folder.children if c.name == "_project.txt")
        self.assertIn("Slug: casa-arvore-2", config.text)
        self.assertIn("casa-arvore-2", self.painel())  # offered to the modal's live check

    def test_a_project_needs_a_stage(self):
        self.connect()
        r = self.create(title="Sem Etapas", stage=["", " "])
        self.assertEqual(r.status_code, 400)
        self.assertIn("A project needs at least one stage.", r.get_data(as_text=True))

    def test_new_project_needs_a_name(self):
        self.connect()
        before = len(self.fake.nodes)
        r = self.client.post("/painel/drive/project", data={"title": "  ", "stage": ["Obra"]})
        self.assertEqual(len(self.fake.nodes), before)
        self.assertEqual(r.status_code, 400)
        self.assertIn("Give the project a name.", r.get_data(as_text=True))

    def test_disconnect_returns_to_the_connect_banner(self):
        self.connect()
        self.client.post("/painel/drive/disconnect")
        html = self.painel()
        self.assertIn("Google Drive disconnected.", html)
        self.assertIn('id="connect-dialog"', html)

    # -- reading projects from the connected folder (drive-oauth mode) -------
    def use_connected_folder(self):
        os.environ["PROJECTS_SOURCE"] = "connection"
        from app import create_app

        self.client = create_app().test_client()
        self.client.post("/painel/login", data={"password": PASSWORD})

    def test_connected_folder_is_the_site_root(self):
        self.use_connected_folder()
        html = self.painel()
        self.assertNotIn("Casa Jardim", html)  # the fixed sample folder is not read
        self.assertIn('id="connect-dialog"', html)

        self.connect()
        self.client.post("/painel/drive/project", data={"title": "Casa Lago", "slug": "casa-lago",
                                                         "stage": ["Estudo", "Obra"]})
        html = self.painel()
        self.assertRegex(html, r'Rascunhos|Drafts')
        self.assertIn("drive-projects__title\">Casa Lago", html)
        self.assertEqual(self.client.get("/casa-lago").status_code, 404)  # drafts stay hidden

        draft = self.node("_Casa Lago")
        self.client.post("/painel/drive/publish", data={"folder_id": draft.id, "title": "Casa Lago"})
        html = self.painel()
        self.assertIn("/casa-lago", html)                       # now in the main list
        self.assertNotIn("drive-projects__title\">Casa Lago", html)  # and no longer a draft
        self.assertEqual(self.client.get("/casa-lago").status_code, 200)

        self.client.post("/painel/drive/disconnect")
        self.assertNotIn("/casa-lago", self.painel())

    # -- office settings ---------------------------------------------------
    def test_settings_change_the_office_name(self):
        self.assertIn("Test Office", self.painel())
        self.client.post("/painel/settings", data={"name": "Estúdio Novo"})
        html = self.painel()
        self.assertIn("Settings saved.", html)
        self.assertIn("· Estúdio Novo</title>", html)
        self.assertNotIn("Test Office", html)

    def test_logo_upload_is_served_and_can_be_removed(self):
        self.client.post("/painel/settings", data={"name": "Test Office", "logo": (BytesIO(PNG), "logo.png")},
                         content_type="multipart/form-data")
        html = self.painel()
        version = re.search(r'/_site/logo\?u=(\d+)', html)
        self.assertIsNotNone(version)
        r = self.client.get(f"/_site/logo?u={version.group(1)}")
        self.assertEqual((r.status_code, r.mimetype, r.data), (200, "image/png", PNG))
        self.assertEqual(r.headers["Content-Security-Policy"], "sandbox")

        self.client.post("/painel/settings", data={"name": "Test Office", "remove_logo": "1"})
        self.assertNotIn("/_site/logo?u=", self.painel())

    def test_logo_that_is_not_an_image_is_refused_and_nothing_changes(self):
        r = self.client.post("/painel/settings",
                             data={"name": "Renamed", "logo": (BytesIO(b"<html>hi</html>"), "logo.png")},
                             content_type="multipart/form-data")
        html = r.get_data(as_text=True)
        self.assertEqual(r.status_code, 400)
        # The modal reopens with the error inside it and what was typed kept.
        self.assertRegex(html, r'id="settings-dialog"[^>]*data-open-on-load')
        self.assertIn('class="field__error" role="alert">That file isn&#39;t a supported image.', html)
        self.assertIn('name="name" value="Renamed"', html)
        self.assertNotIn("Renamed", self.painel())  # nothing was saved

    def test_settings_need_a_name(self):
        r = self.client.post("/painel/settings", data={"name": " "})
        self.assertEqual(r.status_code, 400)
        self.assertIn("Give the office a name.", r.get_data(as_text=True))

    def test_settings_require_login(self):
        self.client.post("/painel/logout")
        self.assertEqual(self.client.post("/painel/settings", data={"name": "X"}).status_code, 401)


class Hosting(PainelBase):
    """Production-only behavior: the www redirect and the Cloud Run storage guard."""

    def test_www_redirects_to_the_main_address_keeping_path_and_query(self):
        r = self.client.get("/casa-jardim?x=1", base_url="http://www.example.com")
        self.assertEqual(r.status_code, 301)
        self.assertEqual(r.location, "http://example.com/casa-jardim?x=1")
        self.assertEqual(self.client.get("/casa-jardim", base_url="http://example.com").status_code, 200)

    def test_www_redirect_uses_https_on_cloud_run(self):
        os.environ["K_SERVICE"] = "portal"
        os.environ["PORTAL_STATE_BUCKET"] = "bucket"  # never reached: the redirect comes first
        from app import create_app

        with mock.patch("arq.oauth_drive.GcsStateStore"), mock.patch("arq.site_settings.GcsStateStore"):
            client = create_app().test_client()
        r = client.post("/painel/drive/connect", base_url="http://www.example.com")
        self.assertEqual(r.location, "https://example.com/painel/drive/connect")

    def test_cloud_run_without_a_bucket_switches_off_connection_and_settings(self):
        os.environ["K_SERVICE"] = "portal"
        os.environ.pop("PORTAL_STATE_BUCKET", None)
        from app import create_app

        with self.assertLogs("app", level="WARNING"):
            client = create_app().test_client()
        client.post("/painel/login", data={"password": PASSWORD})
        html = client.get("/painel").get_data(as_text=True)
        self.assertNotIn('id="connect-dialog"', html)
        self.assertNotIn('data-open-dialog="settings-dialog"', html)
        self.assertEqual(client.post("/painel/settings", data={"name": "X"}).status_code, 404)
        self.assertEqual(client.post("/painel/drive/connect").status_code, 404)


class FakeGoogleGrant(unittest.TestCase):
    """The fake mirrors drive.file: the grant sees only what it created."""

    def setUp(self):
        self.fake = FakeDrive("http://fake", example_language="en")
        self.client = self.fake.app().test_client()
        self.auth = {"Authorization": f"Bearer {OAUTH_TOKEN}"}

    def test_grant_lists_only_app_created_files(self):
        q = f"'{self.fake.root_id}' in parents and trashed=false"
        self.assertEqual(self.client.get("/drive/v3/files", query_string={"q": q},
                                         headers=self.auth).json["files"], [])
        made = self.client.post("/drive/v3/files", headers=self.auth, json={
            "name": "Mine", "mimeType": FOLDER, "parents": [self.fake.root_id]}).json
        names = [f["name"] for f in self.client.get("/drive/v3/files", query_string={"q": q},
                                                    headers=self.auth).json["files"]]
        self.assertEqual(names, ["Mine"])
        self.assertTrue(made["id"].startswith("oauth-"))

    def test_sharing_fails_once_a_foreign_file_is_inside(self):
        r = self.client.post(f"/drive/v3/files/{self.fake.root_id}/permissions", headers=self.auth,
                             json={"role": "reader", "type": "user", "emailAddress": "sa@x"})
        self.assertEqual(r.status_code, 403)
        self.assertIn("appNotAuthorizedToChild", r.get_data(as_text=True))


class LogoSniffing(unittest.TestCase):
    def test_accepted_types(self):
        self.assertEqual(site_settings.sniff_logo(PNG), "image/png")
        self.assertEqual(site_settings.sniff_logo(b"\xff\xd8\xff\xe0rest"), "image/jpeg")
        self.assertEqual(site_settings.sniff_logo(b"RIFF\0\0\0\0WEBPVP8 "), "image/webp")
        self.assertEqual(site_settings.sniff_logo(b'<?xml version="1.0"?>\n<svg xmlns="x"/>'), "image/svg+xml")

    def test_refused(self):
        with self.assertRaises(site_settings.InvalidLogo) as e:
            site_settings.sniff_logo(b"GIF89a")
        self.assertEqual(e.exception.key, "settings.logo_bad_type")
        with self.assertRaises(site_settings.InvalidLogo) as e:
            site_settings.sniff_logo(PNG + b"\0" * site_settings.LOGO_MAX_BYTES)
        self.assertEqual(e.exception.key, "settings.logo_too_big")

    def test_unreadable_store_falls_back_to_the_default_name(self):
        class Broken:
            def load(self):
                raise OSError("bucket unreachable")

        self.assertEqual(site_settings.SiteSettings(Broken(), default_name="Office").name(), "Office")
        self.assertIsNone(site_settings.SiteSettings(Broken(), default_name="Office").logo())


if __name__ == "__main__":
    unittest.main()
