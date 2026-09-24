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

    def test_download_binary_attachment(self):
        r = self.client.get(f"/casa-jardim/f/{self.id_of('Model.skp')}")
        self.assertEqual(r.status_code, 200)
        self.assertIn("attachment", r.headers["Content-Disposition"])
        self.assertEqual(len(r.data), 18_700_000)

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
