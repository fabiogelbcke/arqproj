"""A project's stages as they read: a built-in stage in the office's language, in
its type's own words where it has them; one written by the office as typed."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.projects.models import Project, ProjectStage, ProjectTypeStage, StageDef
from backend.tenancy.models import Locale


@dataclass(frozen=True)
class StageText:
    stage: ProjectStage
    title: str
    about: str | None


def in_language(texts: dict[str, str], locale: Locale) -> str:
    return texts.get(locale.value) or texts[Locale.PT_BR.value]


async def stage_texts(db: AsyncSession, project: Project, locale: Locale) -> list[StageText]:
    """The project's stages in their order."""
    out = []
    for stage, titles, general, own in await db.execute(
        select(ProjectStage, StageDef.titles, StageDef.about, ProjectTypeStage.about)
        .outerjoin(StageDef, StageDef.key == ProjectStage.builtin_key)
        .outerjoin(
            ProjectTypeStage,
            (ProjectTypeStage.stage_key == ProjectStage.builtin_key)
            & (ProjectTypeStage.project_type == project.project_type),
        )
        .where(ProjectStage.project_id == project.id)
        .order_by(ProjectStage.position)
    ):
        if stage.builtin_key is None:  # written by the office, shown as typed
            out.append(StageText(stage, stage.title, stage.about))
        else:
            about = own or general  # the type's own words, else the general text
            out.append(StageText(stage, in_language(titles, locale), in_language(about, locale)))
    return out
