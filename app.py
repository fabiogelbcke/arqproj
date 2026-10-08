"""Architecture project portal, driven by a Google Drive folder tree."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from datetime import timedelta
from functools import wraps
from urllib.parse import quote

from flask import Flask, Response, abort, flash, redirect, render_template, request, session, url_for

from arq import i18n
from arq.drive import Drive, DriveFile, NotDownloadable
from arq.google_auth import get_auth
from arq.projects import ProjectStore

# Types safe to show in the browser. Everything else downloads.
# (SVG deliberately excluded: it can carry script.)
_INLINE_PREFIXES = ("application/pdf", "image/png", "image/jpeg", "image/gif", "image/webp", "video/", "text/plain")
# Images this small are served directly when Drive has no thumbnail for them.
_DIRECT_THUMB_MAX = 8 * 1024 * 1024


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def create_app(store: ProjectStore | None = None) -> Flask:
    logging.basicConfig(level=logging.INFO)
    app = Flask(__name__)

    if store is None:
        store = ProjectStore(
            Drive(get_auth()),
            os.environ.get("DRIVE_ROOT_FOLDER_ID", ""),
            ttl_seconds=float(os.environ.get("CACHE_TTL_SECONDS", "60")),
        )
    site_name = os.environ.get("SITE_NAME", "Studio")
    show_index = _env_flag("SHOW_PROJECT_INDEX")
    dashboard_password = os.environ.get("DASHBOARD_PASSWORD", "")

    # Sessions are only used by the dashboard. The signing key is derived from the
    # password, so changing the password signs everyone out, and there's no
    # second secret to manage.
    app.secret_key = hashlib.sha256(b"arq-portal-session:" + dashboard_password.encode()).digest()
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=bool(os.environ.get("K_SERVICE")),  # HTTPS on Cloud Run
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    )

    app.jinja_env.globals.update(t=i18n.t, site_name=site_name, lang=i18n.lang, logo=store.logo)
    app.jinja_env.filters.update(
        date=i18n.fmt_date,
        filesize=i18n.fmt_size,
        files=i18n.fmt_files,
        type_label=i18n.type_label,
        category=i18n.category,
        is_new=i18n.is_new,
    )
    app.jinja_env.tests["new"] = i18n.is_new

    @app.after_request
    def security_headers(resp: Response) -> Response:
        resp.headers.setdefault("X-Robots-Tag", "noindex, nofollow")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")  # keep project URLs out of Referer
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        return resp

    # -- Public pages ------------------------------------------------------

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

    @app.get("/_site/logo")
    def site_logo():
        f = store.logo(dark=request.args.get("v") == "dark")
        if f is None:
            abort(404)
        upstream, content_type, _ = store.drive.open_media(f)
        try:
            body = upstream.content
        finally:
            upstream.close()
        return Response(body, content_type=content_type,
                        headers={"Cache-Control": "public, max-age=3600", "Content-Security-Policy": "sandbox"})

    @app.get("/<slug>")
    def project_page(slug: str):
        project = store.load(slug)
        if project is None:
            abort(404)
        return render_template("project.html", project=project)

    def _project_file(slug: str, file_id: str) -> DriveFile:
        project = store.load(slug)
        # Only serve files that belong to this project's page.
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
        # No Content-Length on purpose: the response is sent chunked, which lets
        # Cloud Run stream files past its 32 MiB limit for sized HTTP/1 responses.
        # (Browsers just can't show a percentage while downloading.)

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
        if upstream is not None:
            content_type = upstream.headers.get("Content-Type", "image/jpeg")
        elif f.mime_type in ("image/jpeg", "image/png", "image/webp") and (f.size or 0) <= _DIRECT_THUMB_MAX:
            # e.g. a preview image Drive hasn't generated a thumbnail for yet
            upstream, content_type, _ = store.drive.open_media(f)
        else:
            abort(404)
        try:
            body = upstream.content
        finally:
            upstream.close()
        return Response(body, content_type=content_type,
                        headers={"Cache-Control": "private, max-age=600", "Content-Security-Policy": "sandbox"})

    # -- Architect dashboard -----------------------------------------------

    def dashboard_login_required(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not dashboard_password:
                abort(404)  # dashboard disabled
            if not session.get("dashboard"):
                return render_template("login.html"), 401
            return view(*args, **kwargs)

        return wrapper

    @app.get("/painel")
    @dashboard_login_required
    def dashboard():
        root_error = None
        try:
            projects = store.load_all()
        except Exception as exc:  # the root folder itself is unreadable
            logging.getLogger(__name__).exception("dashboard: cannot load projects")
            from arq.projects import describe_error

            key, params = describe_error(exc)
            projects, root_error = [], i18n.t("dash.root_error", reason=key, **params)
        return render_template("dashboard.html", projects=projects, root_error=root_error,
                               base_url=request.url_root.rstrip("/"))

    @app.post("/painel/login")
    def dashboard_login():
        if not dashboard_password:
            abort(404)
        given = request.form.get("password", "")
        if hmac.compare_digest(given.encode(), dashboard_password.encode()):
            session.clear()
            session["dashboard"] = True
            session.permanent = True
            return redirect(url_for("dashboard"))
        time.sleep(1)  # slow down guessing
        flash(i18n.t("dash.wrong_password"))
        return render_template("login.html"), 401

    @app.post("/painel/logout")
    def dashboard_logout():
        session.clear()
        return redirect(url_for("dashboard"))

    @app.post("/painel/refresh")
    @dashboard_login_required
    def dashboard_refresh():
        store.refresh()
        flash(i18n.t("dash.refreshed"))
        return redirect(url_for("dashboard"))

    # -- Errors --------------------------------------------------------------

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("message.html", title=i18n.t("not_found.title"), body=i18n.t("not_found.body")), 404

    @app.errorhandler(500)
    def server_error(_e):
        return render_template("message.html", title=i18n.t("error.title"), body=i18n.t("error.body")), 500

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=_env_flag("DEBUG"))
