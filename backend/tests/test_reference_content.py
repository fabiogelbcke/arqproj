"""Built-in content lives in reference tables (migrations 0008, 0013); the code's enums
name those rows. These tests keep the two in step and the texts complete."""

from enum import StrEnum

import pytest
from sqlalchemy import select, update

from backend.projects.enums import BuiltinStage, DetailKey, DetailType, ProjectType
from backend.projects.models import (
    DetailTypeDef,
    ProjectTypeDef,
    ProjectTypeStage,
    StageDef,
)
from backend.tenancy.models import Locale
from backend.tests import test_office
from backend.tests.test_office import ALINEA

owner = test_office.owner  # fixtures

pytestmark = pytest.mark.anyio

ROWS_AND_ENUMS = [
    (ProjectTypeDef, ProjectType),
    (StageDef, BuiltinStage),
    (DetailTypeDef, DetailKey),
]


async def assert_in_step(session, model, enum: type[StrEnum]):
    rows = set(await session.scalars(select(model.key)))
    members = {member.value for member in enum}
    assert rows == members, (
        f"{model.__tablename__}: rows without enum member {rows - members}, "
        f"enum members without row {members - rows}"
    )


@pytest.mark.parametrize(
    ("model", "enum"), ROWS_AND_ENUMS, ids=lambda x: getattr(x, "__name__", "")
)
async def test_every_built_in_row_has_its_enum_name_and_back(db_session, model, enum):
    await assert_in_step(db_session, model, enum)


async def test_the_step_check_catches_a_missing_row(db_session):
    """Self-test: an enum member added without its migration row fails."""

    class Extended(StrEnum):
        ARCHITECTURE = "architecture"
        INTERIORS = "interiors"
        RENOVATION = "renovation"
        LANDSCAPING = "landscaping"
        POOLS = "pools"

    with pytest.raises(AssertionError, match="pools"):
        await assert_in_step(db_session, ProjectTypeDef, Extended)


async def test_every_built_in_text_exists_in_every_language(db_session):
    texts = [row.labels for row in await db_session.scalars(select(ProjectTypeDef))]
    # A listed stage may have no words of its type's: its general text is used (A44).
    texts += [
        row.about
        for row in await db_session.scalars(select(ProjectTypeStage))
        if row.about is not None
    ]
    texts += [row.labels for row in await db_session.scalars(select(DetailTypeDef))]
    for stage in await db_session.scalars(select(StageDef)):
        texts += [stage.titles, stage.about]
    for entry in texts:
        assert all(entry.get(locale.value, "").strip() for locale in Locale), entry


async def usual_stages(session) -> dict[str, list[str]]:
    """Each type's ticked stages as the table holds them, in the shared order."""
    rows = await session.execute(
        select(ProjectTypeStage.project_type, ProjectTypeStage.stage_key)
        .join(StageDef, StageDef.key == ProjectTypeStage.stage_key)
        .where(ProjectTypeStage.usual, ~StageDef.hidden)
        .order_by(StageDef.position)
    )
    stages: dict[str, list[str]] = {}
    for kind, stage in rows:
        stages.setdefault(kind, []).append(stage)
    return stages


async def ticked_in_the_dialog(client) -> dict[str, list[str]]:
    options = (await client.get("/api/project-types", headers=ALINEA)).json()
    return {kind["key"]: kind["stages"] for kind in options["types"] if kind["stages"]}


async def test_each_type_ticks_the_stages_its_rows_mark_usual(client, owner, db_session):
    """A new project's dialog ticks, for each type, whatever
    `project_type_stages.usual` says (A27). The list itself is content operators
    edit since A44, so it isn't restated here."""
    assert await ticked_in_the_dialog(client) == await usual_stages(db_session)
    # The self-test: a row changed in the table changes what the dialog ticks.
    await db_session.execute(
        update(ProjectTypeStage)
        .where(
            ProjectTypeStage.project_type == ProjectType.ARCHITECTURE,
            ProjectTypeStage.stage_key == BuiltinStage.BRIEFING,
        )
        .values(usual=False)
    )
    ticked = await ticked_in_the_dialog(client)
    assert BuiltinStage.BRIEFING not in ticked[ProjectType.ARCHITECTURE]
    assert ticked == await usual_stages(db_session)


async def test_the_shared_order_is_the_enums_order(db_session):
    """One order for every project; the enum lists the stages in it."""
    keys = list(await db_session.scalars(select(StageDef.key).order_by(StageDef.position)))
    assert keys == [stage.value for stage in BuiltinStage]


async def test_detail_types_have_their_value_types(db_session):
    types = dict(
        (await db_session.execute(select(DetailTypeDef.key, DetailTypeDef.value_type))).all()
    )
    assert types[DetailKey.SITE_AREA] is DetailType.AREA
    assert types[DetailKey.START_DATE] is DetailType.DATE
    assert types[DetailKey.CLIENT] is DetailType.TEXT
