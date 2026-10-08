"""End-to-end tests against the fake Drive (real HTTP, real JWT signing).

    python -m unittest discover -s tests -v
"""

import os
import sys
import threading
import unittest

from werkzeug.serving import make_server

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arq.config import parse_config  # noqa: E402
from arq.projects import parse_stage_name  # noqa: E402
from tools.fake_drive import FakeDrive, service_account_json  # noqa: E402

PORT = 8799


class ConfigParsing(unittest.TestCase):
    def test_header_and_description(self):
        cfg = parse_config("﻿Título: Casa X\r\nCliente: Ana\r\nEtapa atual: 2\r\n\r\nPara 1\r\n- a\r\n* b\r\nPara 2")
        self.assertEqual(cfg.title, "Casa X")
        self.assertEqual(cfg.current_stage, "2")
        self.assertEqual(cfg.details, [("Cliente", "Ana")])
        self.assertEqual([(b.kind, b.items) for b in cfg.description],
                         [("p", ["Para 1"]), ("ul", ["a", "b"]), ("p", ["Para 2"])])

    def test_no_header(self):
        cfg = parse_config("Just a description with no fields.")
        self.assertIsNone(cfg.title)
        self.assertEqual(cfg.description[0].items, ["Just a description with no fields."])

    def test_url_line_is_not_a_field(self):
        cfg = parse_config("Title: A\nhttps://example.com is the site")
        self.assertEqual(cfg.title, "A")
        self.assertEqual(len(cfg.description), 1)

    def test_root_folder_id_validation(self):
        from arq.projects import ProjectStore
        store = ProjectStore(None, "https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWxYz?usp=sharing")
        self.assertEqual(store.root_id, "1AbCdEfGhIjKlMnOpQrStUvWxYz")
        with self.assertRaisesRegex(RuntimeError, "not its name"):
            ProjectStore(None, "Projects")

    def test_stage_names(self):
        self.assertEqual(parse_stage_name("01 - Briefing"), (1, "Briefing"))
        self.assertEqual(parse_stage_name("2. Estudo preliminar"), (2, "Estudo preliminar"))
        self.assertEqual(parse_stage_name("3_Executivo"), (3, "Executivo"))
        self.assertEqual(parse_stage_name("Extras"), (None, "Extras"))


class EndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fake = FakeDrive(f"http://127.0.0.1:{PORT}")
        cls.server = make_server("127.0.0.1", PORT, cls.fake.app(), threaded=True)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        os.environ.update(
            GOOGLE_SERVICE_ACCOUNT_KEY=service_account_json(cls.fake),
            DRIVE_API_BASE=f"http://127.0.0.1:{PORT}/drive/v3",
            DRIVE_ROOT_FOLDER_ID=cls.fake.root_id,
            SITE_NAME="Test Studio",
        )
        os.environ.pop("SHOW_PROJECT_INDEX", None)
        from app import create_app

        cls.client = create_app().test_client()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def id_of(self, name):
        return next(n.id for n in self.fake.nodes.values() if n.name == name)

    def test_project_page(self):
        r = self.client.get("/casa-jardim")
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        for text in ("Casa Jardim", "Família Oliveira", "Built area", "Lagoa da Conceição",
                     "Briefing", "Schematic Design", "Construction Documents",
                     "Site photos", "Renders", "Floor plans – rev B.pdf", "No files yet"):
            self.assertIn(text, html)
        # Config keys that drive behavior are not shown as details
        self.assertNotIn("<dt>Slug</dt>", html)
        # Hidden things stay hidden
        for hidden in ("_internal", "Fees.xlsx", "_notes.txt", "_project"):
            self.assertNotIn(hidden, html)
        # Stage statuses from "Current stage: 3"
        self.assertIn("step step--done", html)
        self.assertIn("step step--current", html)
        self.assertIn("step step--upcoming", html)
        self.assertEqual(r.headers["X-Robots-Tag"], "noindex, nofollow")

    def test_folder_name_slug_and_id_lookup(self):
        self.assertEqual(self.client.get("/apartamento-higienopolis").status_code, 200)
        self.assertEqual(self.client.get(f"/{self.id_of('Casa Jardim')}").status_code, 200)

    def test_landing_hides_index_by_default(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("casa-jardim", r.get_data(as_text=True))

    def test_unknown_and_hidden_projects_404(self):
        self.assertEqual(self.client.get("/nope").status_code, 404)
        self.assertEqual(self.client.get("/templates").status_code, 404)

    def test_download_pdf_inline(self):
        r = self.client.get(f"/casa-jardim/f/{self.id_of('Floor plans – rev B.pdf')}")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data.startswith(b"%PDF"))
        self.assertIn("inline", r.headers["Content-Disposition"])
        self.assertIn("filename*=UTF-8''Floor%20plans%20%E2%80%93%20rev%20B.pdf", r.headers["Content-Disposition"])
        self.assertEqual(r.headers["Content-Security-Policy"], "sandbox")

    def test_metadata_server_auth(self):
        from arq.google_auth import MetadataServerAuth, get_auth
        auth = MetadataServerAuth(f"http://127.0.0.1:{PORT}/computeMetadata/v1/instance/service-accounts/default/token")
        self.assertEqual(auth.token(), "fake-access-token")
        saved = {k: os.environ.pop(k, None) for k in ("GOOGLE_SERVICE_ACCOUNT_KEY", "GOOGLE_APPLICATION_CREDENTIALS")}
        os.environ["K_SERVICE"] = "arq-portal"
        try:
            self.assertIsInstance(get_auth(), MetadataServerAuth)
        finally:
            os.environ.pop("K_SERVICE")
            os.environ.update({k: v for k, v in saved.items() if v is not None})

    def test_download_binary_attachment(self):
        r = self.client.get(f"/casa-jardim/f/{self.id_of('Model.skp')}")
        self.assertEqual(r.status_code, 200)
        self.assertIn("attachment", r.headers["Content-Disposition"])
        self.assertEqual(len(r.data), 18_700_000)
        self.assertNotIn("Content-Length", r.headers)  # chunked, for Cloud Run's 32 MiB limit

    def test_native_file_exports_pdf(self):
        r = self.client.get(f"/casa-jardim/f/{self.id_of('Concept presentation')}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.mimetype, "application/pdf")
        self.assertIn("Concept presentation.pdf", r.headers["Content-Disposition"])

    def test_files_are_scoped_to_their_project(self):
        # hidden file, config doc, and another project's file must not be downloadable
        for name in ("Fees.xlsx", "_project", "Planta existente.jpg"):
            self.assertEqual(self.client.get(f"/casa-jardim/f/{self.id_of(name)}").status_code, 404, name)
        self.assertEqual(self.client.get(f"/apartamento-higienopolis/f/{self.id_of('Planta existente.jpg')}").status_code, 200)

    def test_thumbnail(self):
        r = self.client.get(f"/casa-jardim/t/{self.id_of('Courtyard.jpg')}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.mimetype, "image/jpeg")
        self.assertEqual(self.client.get(f"/casa-jardim/t/{self.id_of('Model.skp')}").status_code, 404)


if __name__ == "__main__":
    unittest.main()


class Helpers(unittest.TestCase):
    def test_dates_use_site_timezone(self):
        from datetime import datetime, timezone

        from arq import i18n

        late_utc = datetime(2026, 9, 24, 1, 30, tzinfo=timezone.utc)  # 22:30 on the 23rd in São Paulo
        saved = os.environ.pop("SITE_TIMEZONE", None)
        try:
            self.assertEqual(i18n.fmt_date(late_utc), "23 Sep 2026")
            os.environ["SITE_TIMEZONE"] = "UTC"
            self.assertEqual(i18n.fmt_date(late_utc), "24 Sep 2026")
        finally:
            os.environ.pop("SITE_TIMEZONE", None)
            if saved:
                os.environ["SITE_TIMEZONE"] = saved

    def test_version_parsing(self):
        from arq.projects import parse_version

        self.assertEqual(parse_version("Floor plans – rev B")[:2], ("floor plans", "rev B"))
        self.assertEqual(parse_version("Planta_v02")[:2], ("planta", "v02"))
        self.assertEqual(parse_version("Corte R03")[:2], ("corte", "R03"))
        self.assertEqual(parse_version("Planta revisão 2")[:2], ("planta", "revisão 2"))
        self.assertEqual(parse_version("Tower")[:2], ("tower", None))
        self.assertEqual(parse_version("Site 01")[:2], ("site 01", None))
        self.assertGreater(parse_version("x rev 10")[2], parse_version("x rev 9")[2])


PORT2 = 8798


class Features(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fake = FakeDrive(f"http://127.0.0.1:{PORT2}")
        cls.server = make_server("127.0.0.1", PORT2, cls.fake.app(), threaded=True)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        os.environ.update(
            GOOGLE_SERVICE_ACCOUNT_KEY=service_account_json(cls.fake),
            DRIVE_API_BASE=f"http://127.0.0.1:{PORT2}/drive/v3",
            DRIVE_ROOT_FOLDER_ID=cls.fake.root_id,
            DASHBOARD_PASSWORD="correct horse",
        )
        from app import create_app

        cls.client = create_app().test_client()
        os.environ.pop("DASHBOARD_PASSWORD")

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def id_of(self, name):
        return next(n.id for n in self.fake.nodes.values() if n.name == name)

    def page(self, slug):
        r = self.client.get(f"/{slug}")
        self.assertEqual(r.status_code, 200)
        return r.get_data(as_text=True)

    def test_versions_are_grouped(self):
        html = self.page("casa-jardim")
        self.assertIn("Floor plans – rev B.pdf", html)
        self.assertIn("Previous versions (1)", html)
        self.assertNotIn("Floor plans – rev A.pdf</span>", html)  # not its own card
        # the older version is still downloadable
        r = self.client.get(f"/casa-jardim/f/{self.id_of('Floor plans – rev A.pdf')}")
        self.assertEqual(r.status_code, 200)

    def test_preview_image_replaces_card(self):
        html = self.page("casa-jardim")
        self.assertNotIn("Model.jpg", html)
        preview_id = self.id_of("Model.jpg")
        self.assertIn(f"/casa-jardim/t/{preview_id}", html)
        self.assertEqual(self.client.get(f"/casa-jardim/t/{preview_id}").status_code, 200)
        self.assertIn('href="#i-cad"', html)  # Site plan.dwg gets the CAD icon

    def test_stage_notes(self):
        html = self.page("casa-jardim")
        self.assertIn("Awaiting client feedback", html)
        self.assertIn("incorporates the comments", html)
        self.assertNotIn(">_stage<", html)

    def test_new_badges(self):
        html = self.page("casa-jardim")
        # files changed in the last 7 days: rev B, sections, site plan, model, 3 renders
        self.assertEqual(html.count('class="badge-new"'), 7)

    def test_status_inferred_without_current_stage(self):
        html = self.page("apartamento-higienopolis")
        self.assertRegex(html, r'step step--current">\s*<a href="#stage-01"')
        self.assertRegex(html, r'step step--upcoming">\s*<a href="#stage-02"')

    def test_logo(self):
        html = self.page("casa-jardim")
        self.assertIn('class="brand-logo', html)
        r = self.client.get("/_site/logo")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.mimetype, "image/png")
        self.assertEqual(self.client.get("/_site/logo?v=dark").status_code, 404)

    def test_dashboard_requires_password(self):
        r = self.client.get("/painel")
        self.assertEqual(r.status_code, 401)
        self.assertNotIn("Casa Jardim", r.get_data(as_text=True))
        r = self.client.post("/painel/login", data={"password": "wrong"})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(self.client.post("/painel/refresh").status_code, 401)

    def test_dashboard(self):
        with self.client as c:
            r = c.post("/painel/login", data={"password": "correct horse"})
            self.assertEqual(r.status_code, 302)
            html = c.get("/painel").get_data(as_text=True)
            for text in ("Casa Jardim", "Apartamento Higienópolis", "Loja Centro", "/loja-centro-k3x9",
                         "Schematic Design", "data-copy="):
                self.assertIn(text, html)
            # warnings
            self.assertIn("No _project doc", html)                       # Apartamento
            self.assertIn("1 file(s) directly in the project folder", html)  # Apartamento/Contrato.pdf
            self.assertIn("“Current stage: Executivo” doesn&#39;t match", html)  # Loja Centro
            self.assertEqual(c.post("/painel/refresh").status_code, 302)
            c.post("/painel/logout")
            self.assertEqual(c.get("/painel").status_code, 401)

    def test_dashboard_disabled_without_password(self):
        from app import create_app

        self.assertEqual(create_app().test_client().get("/painel").status_code, 404)


class ConfigDiagnostics(unittest.TestCase):
    def test_blank_lines_between_fields(self):
        cfg = parse_config("Title: A\n\nClient: B\n\nSlug: a-1\n\nDescription.")
        self.assertEqual((cfg.title, cfg.slug, cfg.details), ("A", "a-1", [("Client", "B")]))
        self.assertEqual(cfg.issues, [])

    def test_known_key_below_description_is_flagged_and_hidden(self):
        cfg = parse_config("Title: A\nSome text.\nSlug: late")
        self.assertIsNone(cfg.slug)
        self.assertEqual(cfg.issues, [("cfg.key_in_description", {"key": "Slug", "line": 3})])
        self.assertEqual([b.items for b in cfg.description], [["Some text."]])

    def test_utf16_and_duplicate_keys(self):
        cfg = parse_config("T\x00i\x00t\x00l\x00e\x00:\x00 \x00A\x00\nSlug: x\nSlug: y")
        self.assertEqual((cfg.title, cfg.slug), ("A", "y"))
        self.assertIn(("cfg.encoding", {}), cfg.issues)
        self.assertIn(("cfg.duplicate_key", {"key": "Slug"}), cfg.issues)

    def test_invalid_slugs_are_flagged_not_rewritten(self):
        for bad in ("!!!", "Casa Nova", "casa nova", "Casa-Nova", "residência-x", "casa--nova", "-casa", "casa_nova"):
            cfg = parse_config(f"Slug: {bad}")
            self.assertEqual(cfg.slug, bad)
            self.assertTrue(cfg.slug_invalid, bad)
            self.assertEqual(cfg.issues, [("cfg.invalid_slug", {"value": bad})])
        for good in ("casa-nova", "casa-nova-7k2p", "a1"):
            self.assertFalse(parse_config(f"Slug: {good}").slug_invalid, good)


PORT3 = 8796


class FailLoudly(unittest.TestCase):
    """Mistakes in Drive must show up in the dashboard, never make projects vanish."""

    @classmethod
    def setUpClass(cls):
        cls.fake = FakeDrive(f"http://127.0.0.1:{PORT3}")
        cls.server = make_server("127.0.0.1", PORT3, cls.fake.app(), threaded=True)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        os.environ.update(
            GOOGLE_SERVICE_ACCOUNT_KEY=service_account_json(cls.fake),
            DRIVE_API_BASE=f"http://127.0.0.1:{PORT3}/drive/v3",
            DRIVE_ROOT_FOLDER_ID=cls.fake.root_id,
            DASHBOARD_PASSWORD="pw",
        )
        from app import create_app

        cls.client = create_app().test_client()
        os.environ.pop("DASHBOARD_PASSWORD")
        cls.client.post("/painel/login", data={"password": "pw"})
        cls.dash = cls.client.get("/painel").get_data(as_text=True)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def id_of(self, name):
        return next(n.id for n in self.fake.nodes.values() if n.name == name)

    def test_duplicate_slug_is_listed_and_flagged(self):
        self.assertIn("Casa Jardim (cópia)", self.dash)
        self.assertIn("HIDDEN FROM CLIENTS: the link /casa-jardim already belongs to “Casa Jardim”", self.dash)
        self.assertIn("“Casa Jardim (cópia)” also asks for the link /casa-jardim", self.dash)
        # the original keeps the link; the copy is reachable by folder ID only
        self.assertIn("Família Oliveira", self.client.get("/casa-jardim").get_data(as_text=True))
        copy = self.client.get(f"/{self.id_of('Casa Jardim (cópia)')}")
        self.assertEqual(copy.status_code, 200)
        self.assertIn("Família Souza", copy.get_data(as_text=True))

    def test_unreadable_folder_is_listed_not_fatal(self):
        self.assertIn("Projeto Externo", self.dash)
        self.assertIn("Couldn&#39;t open this folder: not found or not shared with the site", self.dash)
        self.assertIn("Loja Centro", self.dash)  # the others still load
        self.assertIn("projects need attention", self.dash)

    def test_unreadable_stage_keeps_the_rest_of_the_page(self):
        self.assertIn("Couldn&#39;t open the stage folder “Externo”", self.dash)
        page = self.client.get(f"/{self.id_of('Casa Jardim (cópia)')}").get_data(as_text=True)
        self.assertIn("Programa.pdf", page)

    def test_config_issue_is_shown_and_hidden_from_clients(self):
        self.assertIn("“Etapa atual:” on line 7 of _project is below the description text", self.dash)
        self.assertNotIn("Etapa atual", self.client.get("/loja-centro-k3x9").get_data(as_text=True))


class MoreChecks(FailLoudly):
    """Invalid slugs, duplicate folder names, duplicate stage numbers."""

    def test_invalid_slug_hides_project_and_is_flagged(self):
        self.assertIn("HIDDEN FROM CLIENTS: “Slug: Casa Nova!” isn&#39;t a valid link", self.dash)
        self.assertEqual(self.client.get("/casa-nova").status_code, 404)       # not rewritten into a link
        self.assertEqual(self.client.get(f"/{self.id_of('Casa Nova')}").status_code, 200)  # ID still works

    def test_duplicate_folder_names(self):
        self.assertIn("2 project folders are named “Loja Centro”", self.dash)

    def test_duplicate_stage_numbers_flagged_and_anchors_unique(self):
        self.assertIn("More than one stage is numbered 02: “Anteprojeto”, “Estudo preliminar”", self.dash)
        page = self.client.get("/apartamento-higienopolis").get_data(as_text=True)
        self.assertIn('id="stage-02"', page)
        self.assertIn('id="stage-02-2"', page)


class StatusRules(unittest.TestCase):
    def stages(self, *specs):
        from arq.projects import FileEntry, FileGroup, Stage
        from arq.drive import DriveFile
        out = []
        for i, (num, label, has_files) in enumerate(specs):
            entries = [FileEntry(DriveFile(id=f"f{i}", name="x.pdf", mime_type="application/pdf"))] if has_files else []
            out.append(Stage(folder_id=f"s{i}", number=num, label=label, groups=[FileGroup([], entries)]))
        return out

    def test_ambiguous_current_stage_is_not_guessed(self):
        from arq.projects import assign_statuses
        st = self.stages((1, "Levantamento", True), (2, "Estudo", True), (2, "Anteprojeto", False))
        self.assertEqual(assign_statuses(st, "2"), "ambiguous")
        # falls back to files: last stage with files (the first "2") is current
        self.assertEqual([s.status for s in st], ["done", "current", "upcoming"])
        st = self.stages((1, "Levantamento", True), (2, "Estudo", False), (2, "Anteprojeto", False))
        self.assertEqual(assign_statuses(st, "Anteprojeto"), "ok")  # a name is unambiguous
        self.assertEqual(st[2].status, "current")
        self.assertEqual(assign_statuses(self.stages((1, "A", True)), "9"), "unmatched")
