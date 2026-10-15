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

from arq import i18n, oauth_drive, site_settings
from arq.drive import Drive, DriveFile, NotDownloadable
from arq.google_auth import get_auth
from arq.legal import LEGAL
from arq.config import slugify
from arq.projects import ProjectStore

# Types safe to show in the browser. Everything else downloads.
# (SVG deliberately excluded: it can carry script.)
_INLINE_PREFIXES = ("application/pdf", "image/png", "image/jpeg", "image/gif", "image/webp", "video/", "text/plain")
# Images this small are served directly when Drive has no thumbnail for them.
_DIRECT_THUMB_MAX = 8 * 1024 * 1024

log = logging.getLogger(__name__)


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def create_app(store: ProjectStore | None = None) -> Flask:
    logging.basicConfig(level=logging.INFO)
    app = Flask(__name__)

    # Writes go through the architect's own OAuth grant (drive.file); reads keep
    # going through the service account, which the delivery folder is shared with
    # at creation time. See arq/oauth_drive.py for why it has to be that way.
    oauth_cfg = oauth_drive.OAuthConfig.from_env()
    # On Cloud Run the disk is temporary and there can be several instances, so the
    # Drive connection and office settings need the storage bucket. Without it,
    # switch both features off rather than save things that silently disappear.
    on_cloud_run = bool(os.environ.get("K_SERVICE"))
    durable_state = bool(os.environ.get("PORTAL_STATE_BUCKET", "").strip()) or not on_cloud_run
    if not durable_state:
        log.warning("PORTAL_STATE_BUCKET is not set: Drive connection and office settings are off")
        oauth_cfg = oauth_drive.OAuthConfig("", "", "")
    connection = oauth_drive.Connection(
        oauth_cfg, service_account_email=oauth_drive.service_account_email()
    )
    # Where the site's projects come from: a fixed folder (DRIVE_ROOT_FOLDER_ID), or
    # "connection": the projects folder of the Google Drive connected in the painel.
    projects_from_connection = os.environ.get("PROJECTS_SOURCE", "").strip().lower() == "connection"

    def _connected_root() -> str:
        try:
            return connection.state().get("delivery_folder_id", "")
        except Exception:
            log.exception("cannot read the Drive connection state")
            return ""

    if store is None:
        ttl = float(os.environ.get("CACHE_TTL_SECONDS", "60"))
        if projects_from_connection:
            store = ProjectStore(Drive(get_auth()), "", ttl_seconds=ttl, root_provider=_connected_root)
        else:
            store = ProjectStore(Drive(get_auth()), os.environ.get("DRIVE_ROOT_FOLDER_ID", ""), ttl_seconds=ttl)
    site_name = os.environ.get("SITE_NAME", "ALINEA ARQUITETOS")
    if site_name.upper() in ("STUDIO ALINEA ARQUITETURA", "STUDIO ALÍNEA ARQUITETURA", "STUDIO ALINEA", "STUDIO ALÍNEA"):
        site_name = "ALINEA ARQUITETOS"
    # The office name and logo can be edited in the painel; SITE_NAME is the default.
    settings = site_settings.SiteSettings(default_name=site_name)
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

    app.jinja_env.globals.update(t=i18n.t, lang=i18n.lang, logo=store.logo)

    @app.context_processor
    def office_settings():
        uploaded = settings.logo_version()
        return {"site_name": settings.name(), "uploaded_logo": uploaded,
                "settings_editable": durable_state}

    @app.before_request
    def drop_www():
        # Google sends people back from the Drive sign-in to one fixed address, and
        # the browser keeps cookies for "www." separately; one canonical host avoids
        # a sign-in that looks expired. Also keeps shared links consistent.
        host = request.host
        if host.startswith("www."):
            scheme = "https" if on_cloud_run else request.scheme
            query = request.query_string.decode()
            target = f"{scheme}://{host[4:]}{request.path}" + (f"?{query}" if query else "")
            return redirect(target, 301)
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

    # Linked from Google's OAuth consent screen, which requires both.
    @app.get("/privacidade")
    def privacy():
        return render_template("legal/privacy.html", legal=LEGAL)

    @app.get("/termos")
    def terms():
        return render_template("legal/terms.html", legal=LEGAL)

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.get("/favicon.ico")
    def favicon():
        return Response(status=204)

    @app.get("/_site/logo")
    def site_logo():
        uploaded = settings.logo()
        if uploaded:
            body, content_type = uploaded
            return Response(body, content_type=content_type,
                            headers={"Cache-Control": "public, max-age=3600",
                                     "Content-Security-Policy": "sandbox"})
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
        return _render_dashboard()

    def _render_dashboard(**extra):
        """The painel. `extra` reopens a modal with an error, keeping what was typed."""
        root_error = None
        try:
            projects = store.load_all()
        except Exception as exc:  # the root folder itself is unreadable
            logging.getLogger(__name__).exception("dashboard: cannot load projects")
            from arq.projects import describe_error

            key, params = describe_error(exc)
            projects, root_error = [], i18n.t("dash.root_error", reason=key, **params)
        drive = _drive_context()
        taken = _taken_projects([p.summary for p in projects], drive["drive_projects"])
        return render_template("dashboard.html", projects=projects, root_error=root_error,
                               base_url=request.url_root.rstrip("/"), taken_projects=taken,
                               **drive, **extra)

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
    # Everything lives in the painel: connecting, the projects folder and new
    # projects are modals on the dashboard, not pages of their own.

    def _report(operation: str) -> str:
        """Log the current exception in full; return a short code to show instead.

        The user sees only a translated message and this code (AGENTS.md, "User-facing
        errors"); the code is what lets us find the matching log line.
        """
        ref = secrets.token_hex(3)
        log.error("painel %s failed on %s [ref %s]", operation, request.path, ref, exc_info=True)
        return ref

    def _drive_context() -> dict:
        """What the painel shows about Drive, with each lookup failing on its own."""
        ctx = {
            "drive_configured": oauth_cfg.configured,
            "drive_connected": False,
            "drive_account": None,
            "drive_quota": None,
            "drive_state": {},
            "drive_projects": [],
            "drive_error": None,
            "drive_needs_reconnect": False,
            "default_stages": oauth_drive.DEFAULT_STAGES,
            "projects_from_connection": projects_from_connection,
        }
        if not oauth_cfg.configured:
            return ctx
        try:
            ctx["drive_state"] = connection.state()
            ctx["drive_connected"] = connection.connected
        except Exception:
            ctx["drive_error"] = i18n.t("drive.unavailable", ref=_report("drive state"))
            return ctx
        if not ctx["drive_connected"]:
            return ctx
        try:
            about = connection.writer().about()
            ctx["drive_account"] = about.get("user", {}).get("emailAddress")
            q = about.get("storageQuota", {})
            limit, usage = int(q.get("limit") or 0), int(q.get("usage") or 0)
            ctx["drive_quota"] = {
                "usage": usage,
                "limit": limit,
                "percent": (usage * 100 // limit) if limit else None,
            }
            ctx["drive_projects"] = connection.projects()
        except oauth_drive.NotConnected:
            log.warning("painel: Drive grant no longer valid", exc_info=True)
            ctx["drive_needs_reconnect"] = True
            return ctx
        except Exception:
            ctx["drive_error"] = i18n.t("drive.unavailable", ref=_report("drive lookup"))
            return ctx

        return ctx

    def _taken_projects(summaries, drive_projects) -> dict:
        """Project names and links already in use, so a new project can't repeat them.

        Covers the site's projects (including ones hidden by a problem) and the
        projects in the connected Drive folder, drafts included. Names compare
        without case; links are compared exactly, as the site serves them.
        """
        names, slugs = {}, {}
        for s in summaries:
            for name in (s.title, s.folder_name):
                names[name.strip().casefold()] = s.title
            for slug in (s.slug, s.wanted_slug):
                if slug:
                    slugs[slug] = s.title
        for p in drive_projects:
            names[p["title"].strip().casefold()] = p["title"]
            slugs[p["slug"]] = p["title"]
        return {"names": names, "slugs": slugs}

    def _back_to_painel():
        return redirect(url_for("dashboard"))

    @app.get("/painel/drive")
    @dashboard_login_required
    def drive_panel():
        # The old standalone page; everything is on the dashboard now.
        return _back_to_painel()

    @app.post("/painel/drive/connect")
    @dashboard_login_required
    def drive_connect():
        if not oauth_cfg.configured:
            abort(404)
        state = secrets.token_urlsafe(16)
        session["drive_oauth_state"] = state
        name = (request.form.get("folder_name") or "").strip()[:100]
        session["drive_folder_name"] = name or i18n.t("drive.folder_default")
        return redirect(oauth_drive.authorize_url(oauth_cfg, state))

    @app.get("/painel/drive/callback")
    @dashboard_login_required
    def drive_callback():
        if not oauth_cfg.configured:
            abort(404)
        expected = session.pop("drive_oauth_state", None)
        folder_name = session.pop("drive_folder_name", None) or i18n.t("drive.folder_default")
        if not expected or request.args.get("state") != expected:
            flash(i18n.t("drive.bad_state"), "error")
            return _back_to_painel()
        if request.args.get("error"):
            flash(i18n.t("drive.denied"))
            return _back_to_painel()
        try:
            connection.complete_login(request.args.get("code", ""))
        except Exception:
            flash(i18n.t("drive.connect_failed", ref=_report("drive login")), "error")
            return _back_to_painel()
        store.refresh()
        # The projects folder is required, so create it straight away with the name
        # chosen in the connect modal. If that fails, the dashboard asks again.
        if connection.state().get("delivery_folder_id"):
            flash(i18n.t("drive.connected"))
            return _back_to_painel()
        try:
            connection.setup_delivery_folder(folder_name)
            store.refresh()
            flash(i18n.t("drive.connected_with_folder", name=folder_name))
        except Exception:
            flash(i18n.t("drive.connected"))
            flash(i18n.t("drive.failed", ref=_report("delivery folder")), "error")
        return _back_to_painel()

    @app.post("/painel/drive/setup")
    @dashboard_login_required
    def drive_setup():
        if connection.state().get("delivery_folder_id"):
            return _back_to_painel()  # already there; never create a second one
        name = (request.form.get("name") or "").strip()[:100] or i18n.t("drive.folder_default")
        try:
            connection.setup_delivery_folder(name)
            store.refresh()
            flash(i18n.t("drive.folder_created", name=name))
        except Exception:
            flash(i18n.t("drive.failed", ref=_report("delivery folder")), "error")
        return _back_to_painel()

    @app.post("/painel/drive/project")
    @dashboard_login_required
    def drive_create_project():
        title = (request.form.get("title") or "").strip()[:120]
        slug = slugify(request.form.get("slug") or "")
        stages = [s.strip() for s in request.form.getlist("stage") if s.strip()]

        def again(message):
            # Reopen the modal with the problem and everything that was typed.
            form = {"title": title, "slug": slug, "stages": stages}
            return _render_dashboard(project_error=message, project_form=form), 400

        if not title:
            return again(i18n.t("drive.need_title"))
        if not slugify(slug or title):
            return again(i18n.t("drive.need_slug"))
        if not stages:
            return again(i18n.t("drive.stages_last"))
        if not connection.state().get("delivery_folder_id"):
            flash(i18n.t("drive.need_folder"), "error")
            return _back_to_painel()
        try:
            taken = _taken_projects(store.all_summaries(), connection.projects())
        except Exception:
            return again(i18n.t("drive.failed", ref=_report("check project names")))
        if title.casefold() in taken["names"]:
            return again(i18n.t("drive.name_taken", title=taken["names"][title.casefold()]))
        link = slug or slugify(title)
        if link in taken["slugs"]:
            return again(i18n.t("drive.slug_taken", slug=link, title=taken["slugs"][link]))
        try:
            connection.create_project(title, stages, slug=slug)
            flash(i18n.t("drive.project_created", title=title))
        except Exception:
            flash(i18n.t("drive.failed", ref=_report("create project")), "error")
        return _back_to_painel()

    @app.post("/painel/drive/publish")
    @dashboard_login_required
    def drive_publish():
        try:
            connection.publish_project(request.form["folder_id"], request.form["title"])
            store.refresh()  # so the client site picks it up straight away
            flash(i18n.t("drive.published"))
        except Exception:
            flash(i18n.t("drive.failed", ref=_report("publish project")), "error")
        return _back_to_painel()

    @app.post("/painel/drive/disconnect")
    @dashboard_login_required
    def drive_disconnect():
        connection.disconnect()
        store.refresh()
        flash(i18n.t("drive.disconnected"))
        return _back_to_painel()

    # -- Office settings ---------------------------------------------------

    @app.post("/painel/settings")
    @dashboard_login_required
    def settings_save():
        if not durable_state:
            abort(404)
        name = (request.form.get("name") or "").strip()[:80]

        def again(message):
            # Keep the modal open with what was typed; a file input can't be refilled.
            return _render_dashboard(settings_error=message, settings_name=name), 400

        if not name:
            return again(i18n.t("settings.need_name"))
        upload = request.files.get("logo")
        logo = upload.read(site_settings.LOGO_MAX_BYTES + 1) if upload and upload.filename else None
        try:
            settings.save(name, logo=logo, remove_logo=bool(request.form.get("remove_logo")))
        except site_settings.InvalidLogo as exc:
            return again(i18n.t(exc.key))
        except Exception:
            return again(i18n.t("settings.failed", ref=_report("save settings")))
        flash(i18n.t("settings.saved"))
        return _back_to_painel()

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
