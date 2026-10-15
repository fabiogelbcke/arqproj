"""Built-in content lives in reference tables (migration 0008); the code's enums
name those rows. These tests keep the two in step and the texts complete."""

from enum import StrEnum

import pytest
from sqlalchemy import select

from backend.projects.enums import BuiltinStage, DetailKey, DetailType, ProjectType, StageTemplate
from backend.projects.models import (
    DetailTypeDef,
    ProjectTypeDef,
    StageDef,
    StageTemplateDef,
    TemplateStage,
)
from backend.tenancy.models import Locale

pytestmark = pytest.mark.anyio

ROWS_AND_ENUMS = [
    (ProjectTypeDef, ProjectType),
    (StageTemplateDef, StageTemplate),
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
    texts += [row.labels for row in await db_session.scalars(select(StageTemplateDef))]
    texts += [row.labels for row in await db_session.scalars(select(DetailTypeDef))]
    for stage in await db_session.scalars(select(StageDef)):
        texts += [stage.titles, stage.about, stage.deliverables]
    for entry in texts:
        assert all(entry.get(locale.value, "").strip() for locale in Locale), entry


async def test_the_templates_and_detail_types_are_the_agreed_ones(db_session):
    """What a new project gets from each template, and each detail's value type:
    behaviour later steps rely on (creation, formatting)."""
    stages = {}
    for row in await db_session.scalars(select(TemplateStage).order_by(TemplateStage.position)):
        stages.setdefault(row.template_key, []).append(row.stage_key)
    assert stages[StageTemplate.STANDARD] == [
        BuiltinStage.PROPOSAL,
        BuiltinStage.BRIEFING_SURVEY,
        BuiltinStage.PRELIMINARY_STUDIES,
        BuiltinStage.MODEL_3D,
        BuiltinStage.CONSTRUCTION_DOCUMENTS,
        BuiltinStage.FINAL_DELIVERY,
        BuiltinStage.EXTRA_SERVICES,
    ]
    assert len(stages[StageTemplate.INTERIORS]) == 6
    assert StageTemplate.EMPTY not in stages
    types = dict(
        (await db_session.execute(select(DetailTypeDef.key, DetailTypeDef.value_type))).all()
    )
    assert types[DetailKey.SITE_AREA] is DetailType.AREA
    assert types[DetailKey.START_DATE] is DetailType.DATE
    assert types[DetailKey.CLIENT] is DetailType.TEXT
