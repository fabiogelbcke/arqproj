"""Two fictional tenants, with fictional projects, for local development.

    uv run python -m backend.commands.seed

Then open http://alinea.localhost:8000/ and http://norte.localhost:8000/ (browsers
send every *.localhost address to this machine). Safe to run repeatedly. Only
ever writes to a local database. Real addresses (alineaarquitetos.com, the
staging host) are added to staging and production in step 1.7, not here.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from backend.commands import local_db
from backend.identity.passwords import hash_password
from backend.projects.enums import AccessMode, DetailKey, ProjectStatus, ProjectType
from backend.projects.models import (
    DetailTypeDef,
    Meeting,
    Project,
    ProjectDetail,
    ProjectSlug,
    ProjectStage,
    ProjectTypeStage,
    StageDef,
)
from backend.settings import Settings
from backend.storage.models import StorageConnection, StorageKind
from backend.tenancy.models import Tenant, TenantDomain

SAO_PAULO = timezone(timedelta(hours=-3))
# Fictional projects in Brazilian Portuguese (AGENTS.md), covering the edge cases
# the client page must handle: long names and accents, a project without
# stages, a completed password-protected one, a changed address, an office-written
# stage, past and upcoming meetings. The project password is "demo-senha".
PROJECTS = {
    "alinea": [
        {
            "slug": "casa-jardim",
            "name": "Casa Jardim",
            "client": "Família Oliveira",
            "type": ProjectType.ARCHITECTURE,
            "status": ProjectStatus.ACTIVE,
            "done": 2,  # its first two stages
            "description": (
                "Residência em um terreno inclinado com vista para a Lagoa da Conceição.\n"
                "- Estrutura de concreto aparente com brises de madeira\n"
                "- Ventilação cruzada e beirais amplos"
            ),
            "details": {
                DetailKey.LOCATION: "Florianópolis — SC",
                DetailKey.SITE_AREA: Decimal("1240"),
                DetailKey.BUILT_AREA: Decimal("320"),
                DetailKey.START_DATE: date(2026, 3, 2),
                DetailKey.RESPONSIBLE: "Arq. Marina Carvalho",
            },
            "notes": {2: "Levantamento concluído. Seguimos para o estudo preliminar."},
            "folder": "Casa Jardim",
            "stage_folders": [
                "01 - Briefing",
                "02 - Conceito",
                "03 - Anteprojeto",
                "04 - Desenvolvimento",
                "05 - Projeto Executivo",
            ],
            "meetings": [(-14, "Aprovação do briefing"), (6, "Apresentação do layout")],
        },
        {
            "slug": "apartamento-atlantico",
            "old_slugs": ["apto-atlantico"],
            "name": "Apartamento Atlântico — Copacabana",
            "client": "Clara e Rafael Nogueira",
            "type": ProjectType.INTERIORS,
            "status": ProjectStatus.ACTIVE,
            "done": 2,  # its first two stages
            "description": "Reforma completa de um apartamento de frente para o mar.",
            "details": {
                DetailKey.LOCATION: "Rio de Janeiro — RJ",
                DetailKey.BUILT_AREA: Decimal("148.5"),
                DetailKey.EXPECTED_DELIVERY: date(2026, 12, 18),
            },
            "custom_stage": ("Aprovação no condomínio", "Envio do projeto à administração."),
            "folder": "Apartamento Higienópolis",
            "stage_folders": ["1. Levantamento", "2. Estudo preliminar", "2. Anteprojeto"],
        },
        {
            "slug": "casa-das-oliveiras",
            "name": "Casa das Oliveiras",
            "client": "Família Almeida",
            "type": ProjectType.ARCHITECTURE,
            "stages": [],  # every stage unticked at creation
            "status": ProjectStatus.ACTIVE,
        },
        {
            "slug": "refugio-da-mantiqueira",
            "name": "Refúgio da Mantiqueira",
            "client": "Helena e André",
            "type": ProjectType.LANDSCAPING,
            "status": ProjectStatus.COMPLETED,
            "password": "demo-senha",
            "folder": "Projeto Padrão",
            # Folders kept from an earlier way of working: stage and folder names
            # needn't match (staff may rename either).
            "stage_folders": [
                "01 - Proposta",
                "02 - Briefing e Levantamento",
                "03 - Estudos Preliminares - Anteprojeto",
                "04 - Projeto 3D",
                "05 - Projeto Executivo",
                "06 - Entrega Final",
                "07 - Serviços extras",
            ],
        },
    ],
    "norte": [
        # The same slug as an Alinea project: slugs are per office.
        {
            "slug": "casa-jardim",
            "name": "Casa Jardim (Norte)",
            "client": "Família Rocha",
            "type": ProjectType.ARCHITECTURE,
            "status": ProjectStatus.ACTIVE,
            "folder": "Casa Nova",
            "stage_folders": ["01 - Estudo"],
        },
    ],
}

TENANTS = [
    {
        "slug": "alinea",
        "name": "Alinea (dev)",
        "domains": [("alinea.localhost", True), ("alinea-old.localhost", False)],
    },
    {
        "slug": "norte",
        "name": "Estúdio Norte (dev)",
        "domains": [("norte.localhost", True)],
    },
]


async def seed(session: AsyncSession) -> list[str]:
    """Create any missing tenants and addresses. Returns what was added."""
    added = []
    for spec in TENANTS:
        tenant = await session.scalar(select(Tenant).where(Tenant.slug == spec["slug"]))
        if tenant is None:
            tenant = Tenant(slug=spec["slug"], name=spec["name"])
            session.add(tenant)
            added.append(f"tenant {spec['slug']}")
        for hostname, primary in spec["domains"]:
            exists = await session.scalar(
                select(TenantDomain.id).where(TenantDomain.hostname == hostname)
            )
            if exists is None:
                session.add(TenantDomain(tenant=tenant, hostname=hostname, is_primary=primary))
                added.append(f"address {hostname}")
        await session.flush()
        has_storage = await session.scalar(
            select(StorageConnection.id).where(StorageConnection.tenant_id == tenant.id)
        )
        if not has_storage:
            # Files from the fictional dataset on this machine (folder storage).
            session.add(StorageConnection(tenant_id=tenant.id, kind=StorageKind.FOLDER))
            added.append(f"storage {spec['slug']}")
        for project in PROJECTS.get(spec["slug"], []):
            if await _add_project(session, tenant, project):
                added.append(f"project {spec['slug']}/{project['slug']}")
    await session.commit()
    return added


async def _add_project(session: AsyncSession, tenant: Tenant, spec: dict) -> bool:
    taken = await session.scalar(
        select(ProjectSlug.id).where(
            ProjectSlug.tenant_id == tenant.id, ProjectSlug.slug == spec["slug"]
        )
    )
    if taken:
        return False
    owned = {"tenant_id": tenant.id}
    password = spec.get("password")
    # The type's usual stages, as creation ticks them, unless the spec says otherwise.
    stages = spec.get("stages")
    if stages is None:
        stages = list(
            await session.scalars(
                select(StageDef.key)
                .join(ProjectTypeStage, ProjectTypeStage.stage_key == StageDef.key)
                .where(ProjectTypeStage.project_type == spec["type"])
                .order_by(StageDef.position)
            )
        )
    value_types = dict(
        (await session.execute(select(DetailTypeDef.key, DetailTypeDef.value_type))).all()
    )
    project = Project(
        **owned,
        name=spec["name"],
        client_name=spec["client"],
        project_type=spec["type"],
        status=spec["status"],
        description=spec.get("description", ""),
        access_mode=AccessMode.PASSWORD if password else AccessMode.PUBLIC,
        password_hash=await hash_password(password) if password else None,
        folder_id=spec.get("folder"),
    )
    session.add(project)
    await session.flush()
    owned["project_id"] = project.id
    for old in spec.get("old_slugs", []):
        session.add(ProjectSlug(**owned, slug=old, is_current=False))
    session.add(ProjectSlug(**owned, slug=spec["slug"]))
    notes = spec.get("notes", {})
    stage_folders = spec.get("stage_folders", [])
    # The first `done` stages are completed; all of a completed project's.
    finished = spec["status"] is ProjectStatus.COMPLETED
    done = len(stages) + 1 if finished else spec.get("done", 0)
    for position, key in enumerate(stages, start=1):
        note = notes.get(position, "")
        folder = (
            f"{spec['folder']}/{stage_folders[position - 1]}"
            if position <= len(stage_folders)
            else None
        )
        session.add(
            ProjectStage(
                **owned,
                position=position,
                builtin_key=key,
                notes=note,
                notes_updated_at=datetime.now(SAO_PAULO) if note else None,
                folder_id=folder,
                completed_at=datetime.now(SAO_PAULO) if position <= done else None,
            )
        )
    if custom := spec.get("custom_stage"):
        title, about = custom
        session.add(
            ProjectStage(
                **owned,
                position=len(stages) + 1,
                title=title,
                about=about,
                completed_at=datetime.now(SAO_PAULO) if finished else None,
            )
        )
    columns = {"text": "value_text", "area": "value_number", "date": "value_date"}
    for position, (key, value) in enumerate(spec.get("details", {}).items(), start=1):
        value_type = value_types[key]
        session.add(
            ProjectDetail(
                **owned,
                key=key,
                value_type=value_type,
                position=position,
                **{columns[value_type]: value},
            )
        )
    today = datetime.now(SAO_PAULO).replace(hour=16, minute=0, second=0, microsecond=0)
    for days, title in spec.get("meetings", []):
        start = today + timedelta(days=days)
        session.add(
            Meeting(
                **owned,
                title=title,
                starts_at=start,
                ends_at=start + timedelta(hours=1),
                location="Online",
                link="https://meet.google.com/abc-defg-hij",
            )
        )
    await session.flush()
    return True


async def main() -> None:
    # Tenants are created by the owner: the app's own login can only read them.
    url = Settings().migration_database_url
    local_db.require_local_server(url)  # before writing anything
    engine = create_async_engine(url)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        added = await seed(session)
    await engine.dispose()
    print("Added: " + ", ".join(added) if added else "Nothing to add; already seeded.")


if __name__ == "__main__":
    asyncio.run(main())
