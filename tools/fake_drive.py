"""A fake Google Drive + OAuth token endpoint for local demo and tests.

Implements only what the app uses: the JWT-bearer token exchange (with real
signature verification), files.list by parent, alt=media, export, and
thumbnail links. Serves a small sample architecture project.
"""

from __future__ import annotations

import io
import json
import random
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from flask import Flask, Response, abort, jsonify, request

FOLDER = "application/vnd.google-apps.folder"
DOC = "application/vnd.google-apps.document"
SLIDES = "application/vnd.google-apps.presentation"
SHORTCUT = "application/vnd.google-apps.shortcut"
TOKEN = "fake-access-token"
# Sample dates are relative to startup so "New" badges always show up in the demo.
NOW = datetime.now(timezone.utc).replace(microsecond=0)

CASA_JARDIM = f"""Title: Casa Jardim
Client: Família Oliveira
Tipo de projeto: Projeto Arquitetônico
Location: Florianópolis, SC
Site area: 1,240 m²
Built area: 320 m²
Current stage: 3
Slug: casa-jardim
Reunião agendada: {(NOW + timedelta(days=7)).replace(hour=17, minute=0, second=0).isoformat()}
Fim da reunião: {(NOW + timedelta(days=7)).replace(hour=18, minute=0, second=0).isoformat()}
Assunto da reunião: Apresentação do layout
Local da reunião: Online · Google Meet
Link da reunião: https://meet.google.com/abc-defg-hij

A single-family house on a sloped lot overlooking the Lagoa da Conceição.
The design organizes the living spaces around a planted central courtyard, with the bedroom wing stepping down the terrain to keep views open from every room.
- Exposed concrete structure with timber screens on the west façade
- Cross-ventilation and deep eaves instead of mechanical cooling where possible
- Rainwater collection feeding the courtyard garden
"""

SCHEMATIC_NOTES = """Review meeting: 30 Sep 2026
Status: Awaiting client feedback

Rev B of the floor plans incorporates the comments from the concept review.
Please review the plans and the renders, and send feedback before the meeting.
"""

LOJA_CENTRO = """Title: Loja Centro
Client: Café Aurora
Tipo de projeto: Projeto de Interiores
Current stage: Executivo
Slug: loja-centro-k3x9

Interior fit-out for a 90 m² café in the historic center.
Etapa atual: 2
"""


@dataclass
class Node:
    id: str
    name: str
    mime: str
    parent: str | None
    modified: datetime
    content: bytes = b""
    text: str | None = None  # for Google Docs export
    thumb: bool = False
    target: tuple[str, str] | None = None  # shortcut: (target id, target mime)
    children: list["Node"] = field(default_factory=list)


class FakeDrive:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.nodes: dict[str, Node] = {}
        self._n = 0
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.private_pem = key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        ).decode()
        self.public_key = key.public_key()
        self.root_id = self._build()

    # -- service account key the app should use --------------------------------

    def service_account_info(self) -> dict:
        return {
            "type": "service_account",
            "client_email": "arq-portal@demo-project.iam.gserviceaccount.com",
            "private_key": self.private_pem,
            "token_uri": f"{self.base_url}/token",
        }

    # -- sample tree -------------------------------------------------------------

    def _add(self, name, mime, parent, days_ago=10, **kw) -> Node:
        self._n += 1
        node = Node(
            id=f"demo-{self._n:06d}-sample-folder",
            name=name,
            mime=mime,
            parent=parent.id if parent else None,
            modified=NOW - timedelta(days=days_ago),
            **kw,
        )
        self.nodes[node.id] = node
        if parent:
            parent.children.append(node)
        return node

    def _folder(self, name, parent=None) -> Node:
        return self._add(name, FOLDER, parent)

    def _pdf(self, name, parent, days_ago):
        return self._add(name, "application/pdf", parent, days_ago, content=_tiny_pdf(name), thumb=True)

    def _jpg(self, name, parent, days_ago):
        return self._add(name, "image/jpeg", parent, days_ago, content=_image(name, 1600, 1100), thumb=True)

    def _build(self) -> str:
        root = self._folder("Projects")

        casa = self._folder("Casa Jardim", root)
        self._add("_project", DOC, casa, 3, text=CASA_JARDIM)
        self._add("_notes.txt", "text/plain", casa, 1, content=b"internal: not for clients")
        internal = self._folder("_internal", casa)
        self._add("Fees.xlsx", "application/vnd.ms-excel", internal, 5, content=b"x")

        s1 = self._folder("01 - Briefing", casa)
        self._pdf("Program of needs.pdf", s1, 60)
        self._pdf("Topographic survey.pdf", s1, 58)
        photos = self._folder("Site photos", s1)
        for i in range(1, 4):
            self._jpg(f"Site {i:02d}.jpg", photos, 57)

        s2 = self._folder("02 - Concept", casa)
        self._add("Concept presentation", SLIDES, s2, 35, text="Concept", thumb=True)
        self._jpg("Massing study A.jpg", s2, 36)
        self._jpg("Massing study B.jpg", s2, 36)

        s3 = self._folder("03 - Schematic Design", casa)
        self._add("_stage", DOC, s3, 2, text=SCHEMATIC_NOTES)
        self._pdf("Floor plans – rev A.pdf", s3, 21)
        self._pdf("Floor plans – rev B.pdf", s3, 4)
        self._pdf("Sections and elevations.pdf", s3, 6)
        self._add("Site plan.dwg", "image/vnd.dwg", s3, 6, content=b"AC1032" + b"\0" * 2_400_000)
        self._add("Model.skp", "application/octet-stream", s3, 5, content=b"\0" * 18_700_000)
        self._jpg("Model.jpg", s3, 5)  # preview for Model.skp
        renders = self._folder("Renders", s3)
        for name in ("Living room.jpg", "Courtyard.jpg", "Façade at dusk.jpg"):
            self._jpg(name, renders, 3)

        self._folder("04 - Design Development", casa)
        self._folder("05 - Construction Documents", casa)

        apt = self._folder("Apartamento Higienópolis", root)
        self._pdf("Contrato.pdf", apt, 30)  # loose file in project root → dashboard warning
        a1 = self._folder("1. Levantamento", apt)
        self._jpg("Planta existente.jpg", a1, 20)
        self._folder("2. Estudo preliminar", apt)
        self._folder("2. Anteprojeto", apt)  # two stages numbered 2 → flagged

        loja = self._folder("Loja Centro", root)
        self._add("_project", DOC, loja, 12, text=LOJA_CENTRO)
        l1 = self._folder("01 - Estudo preliminar", loja)
        self._pdf("Layout.pdf", l1, 12)
        self._folder("02 - Anteprojeto", loja)

        # Common mistakes, so the dashboard has something to flag:
        # a project whose _project was copied from Casa Jardim (same slug) ...
        copy = self._folder("Casa Jardim (cópia)", root)
        self._add("_project", DOC, copy, 1, text=CASA_JARDIM.replace("Família Oliveira", "Família Souza"))
        c1 = self._folder("01 - Briefing", copy)
        self._pdf("Programa.pdf", c1, 1)
        self._add("02 - Externo", SHORTCUT, copy, 1, target=("not-shared-stage-0000000000", FOLDER))
        # ... an invalid slug (never rewritten, just flagged) ...
        nova = self._folder("Casa Nova", root)
        self._add("_project", DOC, nova, 1, text="Title: Casa Nova\nSlug: Casa Nova!\n\nA new house.")
        self._pdf("Estudo.pdf", self._folder("01 - Estudo", nova), 1)
        # ... a second folder with the same name as an existing project ...
        self._folder("Loja Centro", root)
        # ... and a shortcut to a folder the site account can't see.
        self._add("Projeto Externo", SHORTCUT, root, 2,
                  target=("not-shared-folder-000000000", FOLDER))

        site = self._folder("_site", root)
        self._add("logo.png", "image/png", site, 30, content=_logo_png(), thumb=False)

        self._folder("_templates", root)
        return root.id

    # -- HTTP --------------------------------------------------------------------

    def _file_json(self, n: Node) -> dict:
        d = {"id": n.id, "name": n.name, "mimeType": n.mime,
             "modifiedTime": n.modified.isoformat().replace("+00:00", "Z"), "hasThumbnail": n.thumb}
        if n.content and n.mime != FOLDER:
            d["size"] = str(len(n.content))
        if n.thumb:
            d["thumbnailLink"] = f"{self.base_url}/thumb/{n.id}=s220"
        if n.target:
            d["shortcutDetails"] = {"targetId": n.target[0], "targetMimeType": n.target[1]}
        return d

    def app(self) -> Flask:
        app = Flask("fake_drive")

        def require_auth():
            if request.headers.get("Authorization") != f"Bearer {TOKEN}":
                abort(401)

        @app.post("/token")
        def token():
            assert request.form["grant_type"] == "urn:ietf:params:oauth:grant-type:jwt-bearer"
            claims = jwt.decode(request.form["assertion"], self.public_key, algorithms=["RS256"],
                                audience=f"{self.base_url}/token")
            assert claims["scope"] == "https://www.googleapis.com/auth/drive.readonly"
            return jsonify(access_token=TOKEN, expires_in=3600, token_type="Bearer")

        @app.get("/computeMetadata/v1/instance/service-accounts/default/token")
        def metadata_token():
            if request.headers.get("Metadata-Flavor") != "Google":
                abort(403)
            assert request.args.get("scopes") == "https://www.googleapis.com/auth/drive.readonly"
            return jsonify(access_token=TOKEN, expires_in=3599, token_type="Bearer")

        @app.get("/drive/v3/files")
        def list_files():
            require_auth()
            m = re.match(r"^'([^']+)' in parents and trashed = false$", request.args.get("q", ""))
            if not m or m.group(1) not in self.nodes:
                abort(404)
            kids = sorted(self.nodes[m.group(1)].children, key=lambda n: n.name.lower())
            return jsonify(files=[self._file_json(n) for n in kids])

        @app.get("/drive/v3/files/<file_id>")
        def media(file_id):
            require_auth()
            n = self.nodes.get(file_id) or abort(404)
            if request.args.get("alt") != "media" or n.mime.startswith("application/vnd.google-apps."):
                abort(400)
            return Response(n.content, content_type=n.mime)

        @app.get("/drive/v3/files/<file_id>/export")
        def export(file_id):
            require_auth()
            n = self.nodes.get(file_id) or abort(404)
            if request.args.get("mimeType") == "text/plain":
                return Response("﻿" + (n.text or "").replace("\n", "\r\n"), content_type="text/plain")
            return Response(_tiny_pdf(n.name), content_type="application/pdf")

        @app.get("/thumb/<path:spec>")
        def thumb(spec):
            require_auth()
            file_id, _, size = spec.partition("=s")
            n = self.nodes.get(file_id) or abort(404)
            s = int(size or 220)
            if n.mime == "application/pdf" or n.mime == SLIDES:
                img = _sheet(n.name, s, int(s * 0.72) if n.mime == SLIDES else int(s * 0.75))
            else:
                img = _image(n.name, s, int(s * 0.69))
            return Response(img, content_type="image/jpeg")

        return app


# -- sample content -----------------------------------------------------------

def _image(seed: str, w: int, h: int) -> bytes:
    """Abstract 'architectural' image: sky gradient, ground, a few volumes."""
    from PIL import Image, ImageDraw

    rnd = random.Random(seed)
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    top, bottom = (rnd.randint(150, 200), rnd.randint(170, 210), rnd.randint(195, 230)), (236, 228, 214)
    horizon = int(h * rnd.uniform(0.55, 0.7))
    for y in range(horizon):
        t = y / horizon
        d.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    d.rectangle([0, horizon, w, h], fill=(rnd.randint(95, 125), rnd.randint(105, 130), 90))
    x = int(w * rnd.uniform(0.05, 0.2))
    for _ in range(rnd.randint(2, 4)):
        bw, bh = int(w * rnd.uniform(0.15, 0.32)), int(h * rnd.uniform(0.18, 0.42))
        tone = rnd.choice([(214, 208, 198), (168, 160, 150), (120, 112, 104), (182, 140, 110)])
        d.rectangle([x, horizon - bh, x + bw, horizon + int(h * 0.04)], fill=tone)
        for wx in range(x + 12, x + bw - 20, max(24, bw // 5)):
            d.rectangle([wx, horizon - bh + 16, wx + 10, horizon - 16], fill=(58, 62, 66))
        x += bw + int(w * rnd.uniform(-0.05, 0.04))
        if x > w * 0.85:
            break
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=82)
    return buf.getvalue()


def _sheet(seed: str, w: int, h: int) -> bytes:
    """Looks like a drawing sheet: white paper, border, plan lines."""
    from PIL import Image, ImageDraw

    rnd = random.Random(seed)
    img = Image.new("RGB", (w, h), (252, 252, 250))
    d = ImageDraw.Draw(img)
    m = max(6, w // 30)
    d.rectangle([m, m, w - m, h - m], outline=(60, 60, 60), width=1)
    d.rectangle([w - m - w // 4, h - m - h // 8, w - m, h - m], outline=(60, 60, 60), width=1)
    for _ in range(9):
        x0, y0 = rnd.randint(m * 3, w // 2), rnd.randint(m * 3, h // 2)
        x1, y1 = x0 + rnd.randint(w // 8, w // 3), y0 + rnd.randint(h // 8, h // 3)
        d.rectangle([x0, y0, min(x1, w - m * 3), min(y1, h - m * 4)], outline=(40, 40, 40), width=2)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def _logo_png() -> bytes:
    """A plain wordmark standing in for the firm's logo."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGBA", (520, 80), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default(size=40)
    except TypeError:  # Pillow < 10.1
        font = ImageFont.load_default()
    d.rectangle([0, 14, 52, 66], outline=(155, 90, 58), width=4)
    d.line([0, 66, 52, 14], fill=(155, 90, 58), width=4)
    d.text((72, 18), "ATELIER DEMO", fill=(27, 26, 24), font=font)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _tiny_pdf(title: str) -> bytes:
    text = title.encode("latin-1", "replace").decode("latin-1").replace("(", "[").replace(")", "]")
    stream = f"BT /F1 24 Tf 72 720 Td ({text}) Tj ET".encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = io.BytesIO(), []
    out.write(b"%PDF-1.4\n")
    for i, body in enumerate(objs, 1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % i + body + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1))
    for off in offsets:
        out.write(b"%010d 00000 n \n" % off)
    out.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref))
    return out.getvalue()


def service_account_json(fake: FakeDrive) -> str:
    return json.dumps(fake.service_account_info())
