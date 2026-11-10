"""Rules every route must keep, checked over the whole app so a new route that
forgets one fails here, not in production (issue #210, "Rigidity"):

- it signs someone in, or is listed below as public with the reason;
- a signed-in route that changes something checks the CSRF token (plan section 17);
- the owner-only routes listed below refuse members (A36);
- a route that changes a project refuses an archived one (plan section 22): under
  /api/projects/{project_id}, and staff's under /api/pages/{slug} (the client page);
- every text and list a request body takes has a length limit.

Each rule has a self-test showing it catches a violation, so it cannot silently
stop working.
"""

import types
import typing
from collections.abc import Callable, Iterator

import annotated_types
import pytest
from fastapi import Depends, FastAPI
from fastapi.routing import APIRoute, iter_route_contexts
from pydantic import BaseModel, Field
from sqlalchemy import text

from backend.app import create_app
from backend.settings import Settings
from backend.tenancy.models import Feature
from backend.tests import test_office
from backend.tests.conftest import TEST_DATABASE_URL
from backend.web.access import changeable_project, locked_changeable_project, require_owner
from backend.web.admin import current_operator, operator_with_csrf
from backend.web.auth import (
    current_account,
    current_staff,
    require_csrf,
    require_csrf_account,
)
from backend.web.pages import changeable_page

owner = test_office.owner  # a fixture

APP = create_app(Settings(environment="test", database_url=TEST_DATABASE_URL))
READS = {"GET", "HEAD"}
SIGN_IN = {current_staff, current_account, current_operator}
CSRF = {require_csrf, require_csrf_account, operator_with_csrf}
CHANGEABLE = {changeable_project, locked_changeable_project, changeable_page}

# Routes anyone may call, each with what protects it instead.
PUBLIC = {
    "GET /health": "Cloud Run's health check",
    "GET /api/openapi.json": "the API description, outside production only",
    "GET /api/docs": "the API description, outside production only",
    "GET /docs/oauth2-redirect": "the API description, outside production only",
    # Unio's own pages.
    "GET /": "the landing page, or an office's portfolio",
    "GET /brand/landing.css": "a static file",
    "GET /brand/portfolio.css": "a static file",
    "GET /brand/portfolio.js": "a static file",
    "GET /brand/unio.png": "a static file",
    "GET /tour-projeto": "the example project",
    "GET /share/exemplo": "the example project's share link",
    "GET /privacidade": "the privacy policy",
    "GET /termos": "the terms of use",
    "POST /internal/maintenance": "Cloud Scheduler: a Google-signed token for this service",
    # Signing in, and the links that come by email.
    "POST /api/session": "signing in",
    "POST /api/password-link": "a password link: the token is the permission",
    "POST /api/password": "a password link: the token is the permission",
    "POST /api/password-reset": "asking for a reset email; rate-limited, same answer for all",
    "POST /api/support-session": "an operator's one-time support link (A43)",
    "POST /api/email-confirmation": "the confirmation email's link: the token is the permission",
    "POST /api/auth/google/start": "signing in with Google",
    "GET /api/auth/google/finish": "signing in with Google: checks its own signed state",
    "POST /api/join/check": "the office's shared join link: the token is the permission",
    "POST /api/join": "the office's shared join link: the token is the permission",
    "GET /api/drive/callback": "Google's redirect: signed state, then the owner's own session",
    "GET /api/tenant": "the office's public name, logo and language for any page",
    "GET /api/office/logo": "the office's logo, shown on its public pages",
    # The operator dashboard (A38): its own host and Google sign-in.
    "POST /api/admin/signin": "the operator's Google sign-in",
    "GET /api/auth/google/callback": "the operator's Google sign-in: checks its own state",
    "POST /api/admin/dev-session": "local development only: refused anywhere deployed",
    "GET /admin/{rest:path}": "the operator dashboard's shell, no data",
    "GET /admin": "the operator dashboard's shell, no data",
    "POST /api/office-signup/check": "an office signup link: the token is the permission",
    "POST /api/office-signup/create": "an office signup link: the token is the permission",
    "GET /criar-escritorio": "the office signup page's shell, no data",
    # The staff app's shell: its data comes from signed-in routes.
    "GET /painel/assets/{name:path}": "the staff app's static files",
    "GET /painel/previa": "the preview page: fictional data",
    "GET /painel/{page:path}": "the staff app's shell, no data",
    "GET /painel": "the staff app's shell, no data",
    # The client page (A06): public or behind its password (`pages._readable`);
    # staff, when signed in, act with their CSRF token (`shares._staff_acting`).
    "GET /{slug}": "the client page's shell, behind the page's password",
    "GET /api/pages/{slug}": "the client page, behind its password",
    "GET /api/pages/{slug}/cover": "the client page's cover, behind its password",
    "GET /api/pages/{slug}/proposal.pdf": "the client page's proposal, behind its password",
    "GET /api/pages/{slug}/meeting.ics": "the client page's meeting, behind its password",
    "POST /api/pages/{slug}/unlock": "the page's password; rate-limited",
    "GET /api/pages/{slug}/files": "the client page's files, behind its password",
    "GET /api/pages/{slug}/files/{key}": "a client page's file, behind its password",
    "GET /api/pages/{slug}/files/{key}/thumb": "a client page's file, behind its password",
    "POST /api/pages/{slug}/subscribe": "a client signs up for emails; rate-limited (A32)",
    "POST /api/pages/{slug}/shares": "clients share files too, behind the page's password (A37)",
    "POST /api/pages/{slug}/shares/mine": "a client's own links: the owner keys they hold",
    "POST /api/pages/{slug}/shares/{link_id}/disable": "staff with CSRF, or the link's owner key",
    "POST /api/pages/{slug}/shares/{link_id}/refresh": "staff with CSRF, or the link's owner key",
    "GET /share/{token}": "a share link's shell: the token is the permission (A37)",
    "GET /api/share/{token}": "a share link: the token is the permission (A37)",
    "POST /api/share/{token}/unlock": "a share link's password; rate-limited",
    "GET /api/share/{token}/zip": "a share link: the token is the permission",
    "GET /api/share/{token}/files/{key}": "a share link: the token is the permission",
    "PUT /api/local-uploads/{token}": "local folders only (refused deployed): an encrypted token",
    "GET /api/emails/unsubscribe/{token}": "the email's unsubscribe link: a signed token",
    "POST /api/emails/unsubscribe/{token}": "the email's unsubscribe link: a signed token",
    # The office's portfolio (A45): public once published.
    "GET /api/portfolio/photos/{photo_id}": "a published portfolio's photo",
    "GET /api/portfolio/videos/{video_id}/poster": "a published portfolio's video",
    "GET /api/portfolio/videos/{video_id}": "a published portfolio's video",
}

# Only the office's owners (A36): its details and logo, its team and its Drive.
OWNER_ONLY = {
    "PATCH /api/office",
    "PUT /api/office/logo",
    "PUT /api/office/logo/dark",
    "DELETE /api/office/logo/dark",
    "PUT /api/office/logo/png",
    "POST /api/team/invites",
    "POST /api/team/invites/{user_id}/link",
    "DELETE /api/team/invites/{user_id}",
    "POST /api/team/join-link",
    "DELETE /api/team/join-link",
    "POST /api/drive/connect",
    "DELETE /api/drive",
}

# Routes that change a project yet work while it is archived, and why.
WHILE_ARCHIVED = {
    "PATCH /api/projects/{project_id}": "archives and restores it (A24)",
    "POST /api/projects/{project_id}/publish": "a draft only; any other status, archived "
    "included, is invalid_status_change",
    "POST /api/projects/{project_id}/accept-proposal": "a proposal only; a declined (archived) "
    "one is invalid_status_change until reopened (A42)",
    "POST /api/projects/{project_id}/proposal/preview": "saves nothing: what is on screen",
    "POST /api/projects/{project_id}/proposal/preview-page": "saves nothing: what is on screen",
    "POST /api/projects/{project_id}/stages/{position}/uploads/failed": "changes nothing: "
    "logs an upload the browser could not finish",
}

# Request fields without a length limit, and why.
UNLIMITED = {
    # Whoever merges second removes these lines (the limits are there by then).
    "auth.LoginIn.email": "limits added in the sign-in hardening PR",
    "auth.LoginIn.password": "limits added in the sign-in hardening PR",
    "auth.LinkIn.token": "limits added in the sign-in hardening PR",
    "auth.ResetIn.email": "limits added in the sign-in hardening PR",
    "auth.ChoosePasswordIn.token": "limits added in the sign-in hardening PR",
    "auth.ChoosePasswordIn.password": "limits added in the sign-in hardening PR",
}


# -- reading the app's routes ---------------------------------------------------------


def routes(app: FastAPI) -> Iterator[tuple[str, object, set[Callable]]]:
    """Each route once per method (a GET's HEAD goes with it), as "METHOD path",
    with every dependency it runs, however deep."""
    for context in iter_route_contexts(app.routes):
        route = context.original_route
        calls = set(_calls(context.dependant)) if isinstance(route, APIRoute) else set()
        for method in sorted(set(context.methods or ()) - {"HEAD"} or {"GET"}):
            yield f"{method} {context.path}", context, calls


def _calls(dependant) -> Iterator[Callable]:
    for sub in dependant.dependencies:
        yield sub.call
        yield from _calls(sub)


def bare_app() -> FastAPI:
    """For the self-tests: only the routes the test adds."""
    return FastAPI(openapi_url=None, docs_url=None, redoc_url=None)


def _stale(listed, app: FastAPI) -> set[str]:
    present = {key for key, _route, _calls in routes(app)}
    return {f"{key}: listed, but no such route" for key in listed if key not in present}


# -- signing in and CSRF --------------------------------------------------------------


def sign_in_problems(app: FastAPI, public: dict[str, str]) -> set[str]:
    problems = _stale(public, app)
    for key, _route, calls in routes(app):
        if not calls & SIGN_IN:
            if key not in public:
                problems.add(f"{key}: signs nobody in and is not listed as public")
        elif key in public:
            problems.add(f"{key}: listed as public, but signs in")
        elif key.split()[0] not in READS and not calls & CSRF:
            problems.add(f"{key}: changes something without checking the CSRF token")
    return problems


def test_every_route_signs_in_or_is_public_and_changes_need_csrf():
    assert sign_in_problems(APP, PUBLIC) == set()


def test_the_sign_in_rule_catches_a_route_that_forgets_it():
    app = bare_app()

    @app.get("/api/open")
    async def open_route() -> None: ...

    @app.post("/api/no-csrf")
    async def no_csrf(_staff=Depends(current_staff)) -> None: ...

    @app.post("/api/fine")
    async def fine(_staff=Depends(require_csrf)) -> None: ...

    @app.get("/api/listed")
    async def listed(_staff=Depends(current_staff)) -> None: ...

    assert sign_in_problems(app, {"GET /api/listed": "", "GET /api/gone": ""}) == {
        "GET /api/open: signs nobody in and is not listed as public",
        "POST /api/no-csrf: changes something without checking the CSRF token",
        "GET /api/listed: listed as public, but signs in",
        "GET /api/gone: listed, but no such route",
    }


# -- owners only ----------------------------------------------------------------------


def owner_problems(app: FastAPI, owner_only: set[str]) -> set[str]:
    problems = _stale(owner_only, app)
    for key, _route, calls in routes(app):
        if key in owner_only and require_owner not in calls:
            problems.add(f"{key}: owner-only, without require_owner")
        elif key not in owner_only and require_owner in calls:
            problems.add(f"{key}: requires an owner, but is not listed as owner-only")
    return problems


def test_the_owner_only_routes_require_an_owner():
    assert owner_problems(APP, OWNER_ONLY) == set()


def test_the_owner_rule_catches_a_route_that_forgets_it():
    app = bare_app()

    @app.post("/api/forgot")
    async def forgot(_staff=Depends(require_csrf)) -> None: ...

    @app.post("/api/unlisted")
    async def unlisted(_staff=Depends(require_owner)) -> None: ...

    assert owner_problems(app, {"POST /api/forgot"}) == {
        "POST /api/forgot: owner-only, without require_owner",
        "POST /api/unlisted: requires an owner, but is not listed as owner-only",
    }


# -- archived projects ----------------------------------------------------------------


def project_changes(app: FastAPI) -> Iterator[tuple[str, set[Callable]]]:
    """Changes to one project: in the painel's API, and staff's from the client page
    (the page's public routes, such as a client's share link, are not changes to it)."""
    for key, _route, calls in routes(app):
        method, path = key.split()
        if method in READS:
            continue
        if path.startswith("/api/projects/{project_id}") or (
            path.startswith("/api/pages/{slug}/") and calls & SIGN_IN
        ):
            yield key, calls


def archive_problems(app: FastAPI, while_archived: dict[str, str]) -> set[str]:
    problems = _stale(while_archived, app)
    for key, calls in project_changes(app):
        if key not in while_archived and not calls & CHANGEABLE:
            problems.add(f"{key}: changes a project without a changeable_ dependency")
    return problems


def test_every_project_change_refuses_an_archived_project():
    assert archive_problems(APP, WHILE_ARCHIVED) == set()


def test_the_archive_rule_catches_a_route_that_forgets_it():
    app = bare_app()

    @app.put("/api/projects/{project_id}/forgot")
    async def forgot(project_id: str, _staff=Depends(require_csrf)) -> None: ...

    @app.put("/api/projects/{project_id}/fine")
    async def fine(_project=Depends(changeable_project)) -> None: ...

    @app.get("/api/projects/{project_id}/read")
    async def read(project_id: str, _staff=Depends(current_staff)) -> None: ...

    @app.post("/api/pages/{slug}/forgot")
    async def page_forgot(slug: str, _staff=Depends(require_csrf)) -> None: ...

    @app.post("/api/pages/{slug}/fine")
    async def page_fine(_project=Depends(changeable_page)) -> None: ...

    @app.post("/api/pages/{slug}/clients")
    async def clients(slug: str) -> None: ...  # public: not staff's change

    assert archive_problems(app, {}) == {
        "PUT /api/projects/{project_id}/forgot: changes a project without a changeable_ dependency",
        "POST /api/pages/{slug}/forgot: changes a project without a changeable_ dependency",
    }


@pytest.fixture
async def archived(owner, db_session):
    """Every feature on (their routes answer feature_off otherwise), and the
    seed's Casa Jardim archived."""
    await db_session.execute(
        text("UPDATE tenants SET features = :all WHERE slug = 'alinea'"),
        {"all": [feature.value for feature in Feature]},
    )
    return await db_session.scalar(
        text(
            "UPDATE projects SET archived_from = status, status = 'archived' "
            "WHERE name = 'Casa Jardim' AND tenant_id = "
            "(SELECT id FROM tenants WHERE slug = 'alinea') RETURNING id"
        )
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "key", sorted(key for key, _calls in project_changes(APP) if key not in WHILE_ARCHIVED)
)
async def test_an_archived_project_is_not_changed(client, owner, archived, key):
    """Each route, as sent: the refusal comes before the body is read, so an empty
    request shows it (a route checking later would answer invalid_request)."""
    method, path = key.split()
    # Any key: the refusal comes before the file or comparison is looked up.
    for name, value in (("project_id", archived), ("position", 1), ("slug", "casa-jardim")):
        path = path.replace(f"{{{name}}}", str(value))
    path = path.replace("{key}", "any")
    response = await client.request(method, path, headers=owner)
    assert (response.status_code, response.json()) == (409, {"error": "project_archived"})


# -- length limits --------------------------------------------------------------------


def _options(annotation) -> list:
    """`X | None` as [X]; anything else as itself."""
    if typing.get_origin(annotation) in (typing.Union, types.UnionType):
        return [a for a in typing.get_args(annotation) if a is not type(None)]
    return [annotation]


def _limited(metadata) -> bool:
    return any(isinstance(m, annotated_types.MaxLen) for m in metadata)


def _unlimited_in(annotation, metadata, where: str, seen: set) -> Iterator[str]:
    """Where `annotation` takes a text or a list without a maximum length,
    looking inside lists, dicts and models."""
    for option in _options(annotation):
        if typing.get_origin(option) is typing.Annotated:
            inner, *extra = typing.get_args(option)
            inner_metadata = [m for e in extra for m in getattr(e, "metadata", [e])]
            yield from _unlimited_in(inner, [*metadata, *inner_metadata], where, seen)
            continue
        origin = typing.get_origin(option) or option
        if origin in (str, list, set, tuple, dict) and not _limited(metadata):
            yield where
        if origin in (list, set, tuple):
            for item in typing.get_args(option):
                yield from _unlimited_in(item, [], f"{where}[]", seen)
        elif origin is dict:
            _key, value = typing.get_args(option)
            yield from _unlimited_in(value, [], f"{where}[]", seen)
        elif isinstance(option, type) and issubclass(option, BaseModel) and option not in seen:
            seen.add(option)
            name = f"{option.__module__.rsplit('.', 1)[-1]}.{option.__name__}"
            for field_name, field in option.model_fields.items():
                yield from _unlimited_in(
                    field.annotation, field.metadata, f"{name}.{field_name}", seen
                )


def _body_params(dependant) -> Iterator:
    yield from dependant.body_params
    for sub in dependant.dependencies:
        yield from _body_params(sub)


def unlimited_fields(app: FastAPI, allowed: dict[str, str]) -> set[str]:
    seen: set = set()
    found: set[str] = set()
    for _key, context, _calls in routes(app):
        if isinstance(context.original_route, APIRoute):
            for param in _body_params(context.dependant):
                info = param.field_info
                found |= set(_unlimited_in(info.annotation, info.metadata, param.name, seen))
    return (found - set(allowed)) | {
        f"{name}: listed, but limited" for name in set(allowed) - found
    }


def test_every_text_and_list_a_request_takes_has_a_limit():
    """So no request makes the server hold or work through more than a screen
    could send. Limits the screens show are in `backend/web/limits.py`."""
    assert unlimited_fields(APP, UNLIMITED) == set()


def test_the_limit_rule_catches_a_field_without_one():
    class Line(BaseModel):
        note: str

    class Body(BaseModel):
        name: str | None = None
        tags: list[str] = Field(max_length=5)
        labels: dict[str, str] = Field(default={}, max_length=5)
        lines: list[Line] = Field(max_length=5)
        fine: str = Field(max_length=5)
        many: list[typing.Annotated[str, Field(max_length=5)]] = Field(max_length=5)

    app = bare_app()

    @app.post("/api/thing")
    async def thing(body: Body) -> None: ...

    assert unlimited_fields(app, {"test_route_rules.Body.fine": ""}) == {
        "test_route_rules.Body.name",
        "test_route_rules.Body.tags[]",
        "test_route_rules.Body.labels[]",
        "test_route_rules.Line.note",
        "test_route_rules.Body.fine: listed, but limited",
    }
