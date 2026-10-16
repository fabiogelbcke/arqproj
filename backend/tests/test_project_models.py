"""The project tables' rules, enforced by the database itself."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

from backend.projects.enums import (
    BuiltinStage,
    DetailKey,
    DetailType,
    ProjectStatus,
    ProjectType,
)
from backend.projects.models import Meeting, Project, ProjectDetail, ProjectSlug, ProjectStage
from backend.tests.test_tenancy_models import add_tenant, assert_refused

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 17, 16, 0, tzinfo=UTC)


async def add_project(session, tenant, slug="casa-jardim", **values):
    fields = {
        "tenant_id": tenant.id,
        "name": "Casa Jardim",
        "client_name": "Família Oliveira",
        "project_type": ProjectType.ARCHITECTURE,
    } | values
    project = Project(**fields)
    session.add(project)
    await session.flush()
    if slug:
        session.add(ProjectSlug(tenant_id=tenant.id, project_id=project.id, slug=slug))
        await session.flush()
    return project


@pytest.fixture
async def alinea(db_session):
    return await add_tenant(db_session, "alinea")


@pytest.fixture
async def norte(db_session):
    return await add_tenant(db_session, "norte", "Estúdio Norte")


async def test_a_new_project_starts_as_an_unpublished_draft(db_session, alinea):
    project = await add_project(db_session, alinea)
    await db_session.refresh(project)
    assert (project.status, project.access_mode.value, project.row_version) == (
        ProjectStatus.DRAFT,
        "public",
        1,
    )


# -- addresses (A29) -----------------------------------------------------------


async def test_an_old_slug_can_never_go_to_another_project(db_session, alinea):
    first = await add_project(db_session, alinea, slug="casa-jardim")
    await db_session.execute(
        text("UPDATE project_slugs SET is_current = false WHERE project_id = :p"), {"p": first.id}
    )
    db_session.add(ProjectSlug(tenant_id=alinea.id, project_id=first.id, slug="casa-do-jardim"))
    await db_session.flush()
    second = await add_project(db_session, alinea, slug=None)
    db_session.add(ProjectSlug(tenant_id=alinea.id, project_id=second.id, slug="casa-jardim"))
    await assert_refused(db_session, db_session.flush(), "uq_project_slugs_tenant_id_slug")


async def test_two_offices_can_use_the_same_slug(db_session, alinea, norte):
    await add_project(db_session, alinea, slug="casa-jardim")
    await add_project(db_session, norte, slug="casa-jardim")  # no error


async def test_a_project_has_one_current_slug(db_session, alinea):
    project = await add_project(db_session, alinea, slug="casa-jardim")
    db_session.add(ProjectSlug(tenant_id=alinea.id, project_id=project.id, slug="outro"))
    await assert_refused(db_session, db_session.flush(), "uq_project_slugs_one_current")


@pytest.mark.parametrize(
    ("slug", "constraint"),
    [
        ("painel", "slug_not_reserved"),
        ("api", "slug_not_reserved"),
        ("healthz", "slug_not_reserved"),  # answered by Cloud Run, never the app
        ("Casa Jardim", "slug_format"),
    ],
)
async def test_slugs_are_clean_and_never_a_reserved_path(db_session, alinea, slug, constraint):
    await assert_refused(db_session, add_project(db_session, alinea, slug=slug), constraint)


# -- stages ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("values", "constraint"),
    [
        ({}, "builtin_or_custom"),  # neither
        ({"builtin_key": BuiltinStage.DETAILING, "title": "Layout"}, "builtin_or_custom"),  # both
        ({"builtin_key": BuiltinStage.DETAILING, "about": "…"}, "builtin_texts_translated"),
    ],
)
async def test_a_stage_is_built_in_or_written_by_the_office(db_session, alinea, values, constraint):
    project = await add_project(db_session, alinea)
    db_session.add(ProjectStage(tenant_id=alinea.id, project_id=project.id, position=1, **values))
    await assert_refused(db_session, db_session.flush(), constraint)


async def test_a_built_in_stage_must_exist(db_session, alinea):
    project = await add_project(db_session, alinea)
    db_session.add(
        ProjectStage(tenant_id=alinea.id, project_id=project.id, position=1, builtin_key="nope")
    )
    await assert_refused(db_session, db_session.flush(), "fk_project_stages_builtin_key")


async def test_a_project_uses_a_known_type(db_session, alinea):
    await assert_refused(
        db_session,
        add_project(db_session, alinea, project_type="pools"),
        "fk_projects_project_type",
    )


async def test_stages_can_swap_positions_in_one_change(db_session, alinea):
    project = await add_project(db_session, alinea)
    for position, key in ((1, BuiltinStage.BRIEFING), (2, BuiltinStage.DETAILING)):
        db_session.add(
            ProjectStage(
                tenant_id=alinea.id, project_id=project.id, position=position, builtin_key=key
            )
        )
    await db_session.flush()
    # Uniqueness is checked at commit, so a reorder can pass through a duplicate.
    await db_session.execute(
        text("UPDATE project_stages SET position = 3 - position WHERE project_id = :p"),
        {"p": project.id},
    )
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))  # checks now: fine


async def test_a_stage_cannot_join_another_offices_project(db_session, alinea, norte):
    project = await add_project(db_session, alinea)
    db_session.add(
        ProjectStage(
            tenant_id=norte.id,
            project_id=project.id,
            position=1,
            builtin_key=BuiltinStage.DETAILING,
        )
    )
    await assert_refused(db_session, db_session.flush(), "fk_project_stages_project")


# -- details (A27) ----------------------------------------------------------------


TEXT, AREA, DATE = DetailType.TEXT, DetailType.AREA, DetailType.DATE


@pytest.mark.parametrize(
    ("key", "value_type", "values", "refused_by"),
    [
        (DetailKey.CLIENT, TEXT, {"value_text": "Família Oliveira"}, None),
        (DetailKey.SITE_AREA, AREA, {"value_number": Decimal("1240.5")}, None),
        (DetailKey.START_DATE, DATE, {"value_date": date(2026, 5, 12)}, None),
        # An area is a number, a date a date: the value must be in its type's column.
        (DetailKey.SITE_AREA, AREA, {"value_text": "1.240 m²"}, "value_matches_type"),
        (DetailKey.START_DATE, DATE, {"value_text": "maio"}, "value_matches_type"),
        (
            DetailKey.CLIENT,
            TEXT,
            {"value_text": "x", "value_date": date(2026, 1, 1)},
            "value_matches_type",
        ),
        (DetailKey.CLIENT, TEXT, {}, "value_matches_type"),
        # The row's value type is its detail type's, not the writer's choice.
        (DetailKey.SITE_AREA, TEXT, {"value_text": "1.240 m²"}, "fk_project_details_detail_type"),
        ("shoe_size", TEXT, {"value_text": "42"}, "fk_project_details_detail_type"),
    ],
)
async def test_a_detail_holds_exactly_a_value_of_its_type(
    db_session, alinea, key, value_type, values, refused_by
):
    project = await add_project(db_session, alinea)
    db_session.add(
        ProjectDetail(
            tenant_id=alinea.id,
            project_id=project.id,
            key=key,
            value_type=value_type,
            position=1,
            **values,
        )
    )
    if refused_by is None:
        await db_session.flush()
    else:
        await assert_refused(db_session, db_session.flush(), refused_by)


async def test_a_detail_appears_once_per_project(db_session, alinea):
    project = await add_project(db_session, alinea)
    for position in (1, 2):
        db_session.add(
            ProjectDetail(
                tenant_id=alinea.id,
                project_id=project.id,
                key=DetailKey.LOCATION,
                value_type=DetailType.TEXT,
                position=position,
                value_text="Florianópolis",
            )
        )
    await assert_refused(db_session, db_session.flush(), "uq_project_details_project_id_key")


# -- meetings and limits ------------------------------------------------------------


@pytest.mark.parametrize(
    ("values", "constraint"),
    [
        ({"ends_at": NOW - timedelta(minutes=1)}, "ends_after_start"),
        ({"link": "javascript:alert(1)"}, "link_is_web"),
        ({"link": "meet.google.com/abc"}, "link_is_web"),  # no scheme
        ({"title": "x" * 41}, "title_length"),
        ({"location": "x" * 61}, "location_length"),
    ],
)
async def test_meetings_are_checked(db_session, alinea, values, constraint):
    project = await add_project(db_session, alinea)
    fields = {
        "title": "Apresentação do layout",
        "starts_at": NOW,
        "ends_at": NOW + timedelta(hours=1),
        "link": "https://meet.google.com/abc-defg-hij",
    } | values
    db_session.add(Meeting(tenant_id=alinea.id, project_id=project.id, **fields))
    await assert_refused(db_session, db_session.flush(), constraint)


async def test_a_project_can_have_several_meetings(db_session, alinea):
    project = await add_project(db_session, alinea)
    for days in (0, 7):
        db_session.add(
            Meeting(
                tenant_id=alinea.id,
                project_id=project.id,
                title="Reunião",
                starts_at=NOW + timedelta(days=days),
                ends_at=NOW + timedelta(days=days, hours=1),
            )
        )
    await db_session.flush()


@pytest.mark.parametrize(
    ("values", "constraint"),
    [
        ({"client_name": "x" * 49}, "client_name_length"),
        ({"client_name": "  "}, "client_name_length"),
        ({"access_mode": "password"}, "password_set"),  # password mode without a password
    ],
)
async def test_project_values_are_checked(db_session, alinea, values, constraint):
    await assert_refused(db_session, add_project(db_session, alinea, **values), constraint)


async def test_through_the_app_login_each_office_sees_only_its_projects(db_session):
    """The seed's projects, as the app's restricted login: isolation, and only the
    columns the painel changes may be changed, on the real tables."""
    from backend.commands.seed import seed
    from backend.tests.conftest import RUNTIME_ROLE

    await seed(db_session)
    tenants = dict((await db_session.execute(text("SELECT slug, id FROM tenants"))).all())
    await db_session.execute(text(f'SET ROLE "{RUNTIME_ROLE}"'))
    try:
        seen = {}
        for slug, tenant_id in tenants.items():
            await db_session.execute(
                text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
            )
            seen[slug] = sorted(
                (await db_session.execute(text("SELECT slug FROM project_slugs WHERE is_current")))
                .scalars()
                .all()
            )
        assert seen == {
            "alinea": [
                "apartamento-atlantico",
                "casa-das-oliveiras",
                "casa-jardim",
                "refugio-da-mantiqueira",
            ],
            "norte": ["casa-jardim"],
        }
        # As Norte, a change reaches only Norte's one project.
        await db_session.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenants["norte"])}
        )
        renamed = await db_session.execute(text("UPDATE projects SET name = name || ' '"))
        assert renamed.rowcount == 1
        with pytest.raises(Exception, match="permission denied"):
            await db_session.execute(text("UPDATE projects SET description = 'x'"))
    finally:
        await db_session.rollback()


async def test_one_drive_folder_never_serves_two_offices(db_session, alinea, norte):
    from backend.storage.models import StorageConnection, StorageKind

    for tenant in (alinea, norte):
        db_session.add(
            StorageConnection(
                tenant_id=tenant.id,
                kind=StorageKind.GOOGLE,
                root_id="driveFolder123",
                reader_identity="portal@example.iam",
            )
        )
    await assert_refused(db_session, db_session.flush(), "uq_storage_connections_google_root")
