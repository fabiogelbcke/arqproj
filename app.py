"""Architecture project portal, driven by a Google Drive folder tree."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import time
from datetime import timedelta
from functools import wraps
from urllib.parse import quote

from flask import Flask, Response, abort, flash, redirect, render_template, request, session, url_for

from arq import i18n, oauth_drive
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
    site_name = os.environ.get("SITE_NAME", "ALINEA ARQUITETOS")
    if site_name.upper() in ("STUDIO ALINEA ARQUITETURA", "STUDIO ALÍNEA ARQUITETURA", "STUDIO ALINEA", "STUDIO ALÍNEA"):
        site_name = "ALINEA ARQUITETOS"
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

    @app.get('/<slug>/reuniao.ics')
    def meeting_calendar(slug: str):
        project = store.load(slug)
        if project is None or project.config.meeting is None or not project.config.meeting.upcoming:
            abort(404)
        return Response(project.config.meeting.icalendar(project.title, project.summary.id),
                        content_type='text/calendar; charset=utf-8', headers={
                            'Content-Disposition': 'attachment; filename="reuniao.ics"',
                            'Cache-Control': 'private, no-store',
                        })

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

    # -- Drive connection (OAuth) -------------------------------------------
    # Writes go through the architect's own OAuth grant (drive.file); reads keep
    # going through the service account, which the delivery folder is shared with
    # at creation time. See arq/oauth_drive.py for why it has to be that way.

    oauth_cfg = oauth_drive.OAuthConfig.from_env()
    connection = oauth_drive.Connection(
        oauth_cfg, service_account_email=oauth_drive.service_account_email()
    )

    def _drive_context(**extra):
        """Everything the panel shows, with each lookup failing on its own."""
        ctx = {
            "configured": oauth_cfg.configured,
            "connected": False,
            "account": None,
            "quota": None,
            "state": {},
            "projects": [],
            "service_account": connection.service_account_email,
            "default_stages": oauth_drive.DEFAULT_STAGES,
            "seen_by_service_account": None,
            "error": None,
            "needs_reconnect": False,
        }
        ctx.update(extra)
        if not oauth_cfg.configured:
            return ctx
        try:
            ctx["state"] = connection.state()
            ctx["connected"] = connection.connected
        except Exception as exc:
            ctx["error"] = str(exc)
            return ctx
        if not ctx["connected"]:
            return ctx
        try:
            about = connection.writer().about()
            ctx["account"] = about.get("user", {}).get("emailAddress")
            q = about.get("storageQuota", {})
            limit, usage = int(q.get("limit") or 0), int(q.get("usage") or 0)
            ctx["quota"] = {
                "usage": usage,
                "limit": limit,
                "percent": (usage * 100 // limit) if limit else None,
            }
            ctx["projects"] = connection.projects()
        except oauth_drive.NotConnected as exc:
            ctx["needs_reconnect"] = True
            ctx["error"] = str(exc)
            return ctx
        except Exception as exc:
            ctx["error"] = str(exc)
            return ctx

        # The proof that the whole chain works: what the *service account* can
        # see inside the folder the OAuth grant created and shared with it.
        folder_id = ctx["state"].get("delivery_folder_id")
        if folder_id:
            try:
                ctx["seen_by_service_account"] = [
                    f.name for f in store.drive.list_children(folder_id)
                ]
            except Exception as exc:
                ctx["seen_by_service_account"] = []
                ctx["error"] = ctx["error"] or str(exc)
        return ctx

    @app.get("/painel/drive")
    @dashboard_login_required
    def drive_panel():
        return render_template("drive.html", **_drive_context())

    @app.get("/painel/drive/connect")
    @dashboard_login_required
    def drive_connect():
        if not oauth_cfg.configured:
            abort(404)
        state = secrets.token_urlsafe(16)
        session["drive_oauth_state"] = state
        return redirect(oauth_drive.authorize_url(oauth_cfg, state))

    @app.get("/painel/drive/callback")
    @dashboard_login_required
    def drive_callback():
        if not oauth_cfg.configured:
            abort(404)
        expected = session.pop("drive_oauth_state", None)
        if not expected or request.args.get("state") != expected:
            flash(i18n.t("drive.bad_state"))
            return redirect(url_for("drive_panel"))
        if request.args.get("error"):
            flash(i18n.t("drive.denied"))
            return redirect(url_for("drive_panel"))
        try:
            connection.complete_login(request.args.get("code", ""))
        except Exception as exc:
            logging.getLogger(__name__).exception("drive: login failed")
            flash(i18n.t("drive.connect_failed", detail=str(exc)))
        else:
            flash(i18n.t("drive.connected"))
        return redirect(url_for("drive_panel"))

    @app.post("/painel/drive/setup")
    @dashboard_login_required
    def drive_setup():
        name = (request.form.get("name") or "").strip() or i18n.t("drive.folder_default")
        try:
            connection.setup_delivery_folder(name)
            flash(i18n.t("drive.folder_created", name=name))
        except Exception as exc:
            logging.getLogger(__name__).exception("drive: delivery folder failed")
            flash(i18n.t("drive.failed", detail=str(exc)))
        return redirect(url_for("drive_panel"))

    @app.post("/painel/drive/project")
    @dashboard_login_required
    def drive_create_project():
        title = (request.form.get("title") or "").strip()
        if not title:
            flash(i18n.t("drive.need_title"))
            return redirect(url_for("drive_panel"))
        stages = [s.strip() for s in request.form.getlist("stage") if s.strip()]
        try:
            connection.create_project(title, stages, slug=(request.form.get("slug") or "").strip())
            flash(i18n.t("drive.project_created", title=title))
        except Exception as exc:
            logging.getLogger(__name__).exception("drive: create project failed")
            flash(i18n.t("drive.failed", detail=str(exc)))
        return redirect(url_for("drive_panel"))

    @app.post("/painel/drive/publish")
    @dashboard_login_required
    def drive_publish():
        try:
            connection.publish_project(request.form["folder_id"], request.form["title"])
            store.refresh()  # so the client site picks it up straight away
            flash(i18n.t("drive.published"))
        except Exception as exc:
            logging.getLogger(__name__).exception("drive: publish failed")
            flash(i18n.t("drive.failed", detail=str(exc)))
        return redirect(url_for("drive_panel"))

    @app.post("/painel/drive/disconnect")
    @dashboard_login_required
    def drive_disconnect():
        connection.disconnect()
        flash(i18n.t("drive.disconnected"))
        return redirect(url_for("drive_panel"))

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
