"""The built-in project types and stages as the operator dashboard edits them
(A44): one list for every office, its texts in every language.

Read with any login (reference tables); changed only with the operator's login,
which may write these three tables and nothing else of the kind. How many of each
office's projects use a type or stage is counted office by office with the app's
login, each read scoped to that office (as the dashboard's other counts, A38).
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.db.isolation import scope_to_tenant
from backend.projects.enums import ProjectType
from backend.projects.models import (
    Project,
    ProjectStage,
    ProjectTypeDef,
    ProjectTypeStage,
    StageDef,
)
from backend.tenancy.models import Locale, Tenant

TYPE_LABEL_MAX = 40  # a type's name: it fits its button in the creation form
STAGE_ABOUT_MAX = 1000  # as a proposal's service description, which starts from it
KEY_MAX = 40


class CatalogProblem(Exception):
    """A change the lists refuse; `code` is an ErrorCode value."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def texts(pt: str, en: str, limit: int) -> dict[str, str]:
    """Both languages, trimmed; English left blank takes the Portuguese."""
    pt, en = pt.strip(), en.strip()
    if not pt or len(pt) > limit or len(en) > limit:
        raise CatalogProblem("invalid_setting_text")
    return {Locale.PT_BR.value: pt, Locale.EN.value: en or pt}


def new_key(name: str, taken: set[str]) -> str:
    """A key for a new type or stage, from its Portuguese name: "Pós-Produção" →
    "pos_producao", "pos_producao_2" when taken. Never shown; never changes."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    base = re.sub(r"[^a-z0-9]+", "_", plain).strip("_")[:KEY_MAX].rstrip("_") or "item"
    key, n = base, 2
    while key in taken:
        key, n = f"{base}_{n}", n + 1
    return key


@dataclass
class Usage:
    """Projects (not deleted) per type, per built-in stage, and per stage within a
    type: what an edit of each text reaches."""

    types: Counter[str] = field(default_factory=Counter)
    stages: Counter[str] = field(default_factory=Counter)
    type_stages: Counter[tuple[str, str]] = field(default_factory=Counter)


async def usage(sessionmaker: async_sessionmaker) -> Usage:
    found = Usage()
    async with sessionmaker() as session:
        tenant_ids = list(await session.scalars(select(Tenant.id)))
    for tenant_id in tenant_ids:
        async with sessionmaker() as session:
            scope_to_tenant(session.sync_session, tenant_id)
            for kind, count in await session.execute(
                select(Project.project_type, func.count())
                .where(Project.deleted_at.is_(None))
                .group_by(Project.project_type)
            ):
                found.types[kind] += count
            for kind, stage, count in await session.execute(
                select(Project.project_type, ProjectStage.builtin_key, func.count())
                .join(Project, Project.id == ProjectStage.project_id)
                .where(Project.deleted_at.is_(None), ProjectStage.builtin_key.is_not(None))
                .group_by(Project.project_type, ProjectStage.builtin_key)
            ):
                found.stages[stage] += count
                found.type_stages[(kind, stage)] += count
    return found


async def lists(
    db: AsyncSession,
) -> tuple[list[ProjectTypeDef], list[StageDef], list[ProjectTypeStage]]:
    """The types and the stages in their order, and every stage a type lists."""
    types = list(await db.scalars(select(ProjectTypeDef).order_by(ProjectTypeDef.position)))
    stages = list(await db.scalars(select(StageDef).order_by(StageDef.position)))
    listed = list(await db.scalars(select(ProjectTypeStage)))
    return types, stages, listed


def _same_name(names: list[dict[str, str]], name: str) -> bool:
    return any(n.get(Locale.PT_BR.value, "").casefold() == name.casefold() for n in names)


async def add_type(db: AsyncSession, labels: dict[str, str]) -> str:
    types = list(await db.scalars(select(ProjectTypeDef)))
    if _same_name([t.labels for t in types], labels[Locale.PT_BR.value]):
        raise CatalogProblem("setting_name_taken")
    key = new_key(labels[Locale.PT_BR.value], {t.key for t in types})
    position = max((t.position for t in types), default=0) + 1
    db.add(ProjectTypeDef(key=key, position=position, labels=labels))
    return key


async def add_stage(db: AsyncSession, titles: dict[str, str], about: dict[str, str]) -> str:
    stages = list(await db.scalars(select(StageDef)))
    if _same_name([s.titles for s in stages], titles[Locale.PT_BR.value]):
        raise CatalogProblem("setting_name_taken")
    key = new_key(titles[Locale.PT_BR.value], {s.key for s in stages})
    position = max((s.position for s in stages), default=0) + 1
    db.add(StageDef(key=key, position=position, titles=titles, about=about))
    return key


@dataclass(frozen=True)
class Listed:
    key: str
    usual: bool
    about: dict[str, str] | None  # None: the stage's general text


async def change_type(
    db: AsyncSession, key: str, labels: dict[str, str], hidden: bool, listed: list[Listed]
) -> None:
    """Its name, whether hidden, and every stage it lists (replacing the list)."""
    kind = await db.get(ProjectTypeDef, key, with_for_update=True)
    if kind is None:
        raise CatalogProblem("setting_not_found")
    others = list(await db.scalars(select(ProjectTypeDef).where(ProjectTypeDef.key != key)))
    if _same_name([t.labels for t in others], labels[Locale.PT_BR.value]):
        raise CatalogProblem("setting_name_taken")
    keys = [row.key for row in listed]
    known = set(await db.scalars(select(StageDef.key).where(StageDef.key.in_(keys))))
    if len(set(keys)) != len(keys) or known != set(keys):
        raise CatalogProblem("setting_not_found")
    if key == ProjectType.OTHER:
        # It lists every stage: only the ticked ones are kept.
        listed = [row for row in listed if row.usual]
    kind.labels, kind.hidden = labels, hidden
    await db.execute(delete(ProjectTypeStage).where(ProjectTypeStage.project_type == key))
    db.add_all(
        ProjectTypeStage(project_type=key, stage_key=row.key, usual=row.usual, about=row.about)
        for row in listed
    )


async def change_stage(
    db: AsyncSession, key: str, titles: dict[str, str], about: dict[str, str], hidden: bool
) -> None:
    stage = await db.get(StageDef, key, with_for_update=True)
    if stage is None:
        raise CatalogProblem("setting_not_found")
    others = list(await db.scalars(select(StageDef).where(StageDef.key != key)))
    if _same_name([s.titles for s in others], titles[Locale.PT_BR.value]):
        raise CatalogProblem("setting_name_taken")
    stage.titles, stage.about, stage.hidden = titles, about, hidden


async def reorder(db: AsyncSession, model: type[ProjectTypeDef] | type[StageDef], keys: list[str]):
    """Every type (or stage) in the order given: all of them, each once."""
    rows = {row.key: row for row in await db.scalars(select(model).with_for_update())}
    if len(keys) != len(set(keys)) or set(keys) != set(rows):
        raise CatalogProblem("setting_not_found")
    for position, key in enumerate(keys, start=1):
        rows[key].position = position
