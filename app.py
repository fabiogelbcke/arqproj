"""Architecture project portal, driven by a Google Drive folder tree."""

from __future__ import annotations

import logging
import os
from urllib.parse import quote

from flask import Flask, Response, abort, render_template

from arq import i18n
from arq.drive import Drive, NotDownloadable
from arq.google_auth import ServiceAccountAuth
from arq.projects import ProjectStore

# Types safe to show in the browser. Everything else downloads.
# (SVG deliberately excluded: it can carry script.)
_INLINE_PREFIXES = ("application/pdf", "image/png", "image/jpeg", "image/gif", "image/webp", "video/", "text/plain")


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def create_app(store: ProjectStore | None = None) -> Flask:
    logging.basicConfig(level=logging.INFO)
    app = Flask(__name__)

    if store is None:
        store = ProjectStore(
            Drive(ServiceAccountAuth.from_env()),
            os.environ.get("DRIVE_ROOT_FOLDER_ID", ""),
            ttl_seconds=float(os.environ.get("CACHE_TTL_SECONDS", "60")),
        )
    site_name = os.environ.get("SITE_NAME", "Studio")
    show_index = _env_flag("SHOW_PROJECT_INDEX")

    app.jinja_env.globals.update(t=i18n.t, site_name=site_name, lang=i18n.lang)
    app.jinja_env.filters.update(
        date=i18n.fmt_date, filesize=i18n.fmt_size, files=i18n.fmt_files, type_label=i18n.type_label
    )

    @app.after_request
    def security_headers(resp: Response) -> Response:
        resp.headers.setdefault("X-Robots-Tag", "noindex, nofollow")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")  # keep project URLs out of Referer
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        return resp

    @app.get("/")
    def landing():
        projects = sorted(store.index().values(), key=lambda p: p.title.lower()) if show_index else []
        return render_template("landing.html", projects=projects)

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.get("/favicon.ico")
    def favicon():
        return Response(status=204)

    @app.get("/<slug>")
    def project_page(slug: str):
        project = store.load(slug)
        if project is None:
            abort(404)
        return render_template("project.html", project=project)

    def _project_file(slug: str, file_id: str):
        project = store.load(slug)
        # Only serve files that are visible on this project's page.
        if project is None or file_id not in project.files:
            abort(404)
        return project.files[file_id]

    @app.get("/<slug>/f/<file_id>")
    def download(slug: str, file_id: str):
        f = _project_file(slug, file_id)
        try:
            upstream, content_type, filename = store.drive.open_media(f)
        except NotDownloadable:
            abort(404)
        inline = content_type.startswith(_INLINE_PREFIXES)
        ascii_name = filename.encode("ascii", "replace").decode().replace('"', "'")
        headers = {
            "Content-Disposition": f"{'inline' if inline else 'attachment'}; "
            f"filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}",
            "Cache-Control": "private, max-age=300",
            "Content-Security-Policy": "sandbox",
        }
        if upstream.headers.get("Content-Length"):
            headers["Content-Length"] = upstream.headers["Content-Length"]

        def stream():
            try:
                yield from upstream.iter_content(chunk_size=64 * 1024)
            finally:
                upstream.close()

        return Response(stream(), content_type=content_type, headers=headers)

    @app.get("/<slug>/t/<file_id>")
    def thumbnail(slug: str, file_id: str):
        f = _project_file(slug, file_id)
        upstream = store.drive.open_thumbnail(f)
        if upstream is None:
            abort(404)
        try:
            body = upstream.content
        finally:
            upstream.close()
        return Response(
            body,
            content_type=upstream.headers.get("Content-Type", "image/jpeg"),
            headers={"Cache-Control": "private, max-age=600", "Content-Security-Policy": "sandbox"},
        )

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("message.html", title=i18n.t("not_found.title"), body=i18n.t("not_found.body")), 404

    @app.errorhandler(500)
    def server_error(_e):
        return render_template("message.html", title=i18n.t("error.title"), body=i18n.t("error.body")), 500

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=_env_flag("DEBUG"))
