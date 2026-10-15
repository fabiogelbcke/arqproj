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
from backend.projects.enums import (
    TEMPLATE_PROJECT_TYPE,
    TEMPLATE_STAGES,
    AccessMode,
    DetailKey,
    ProjectStatus,
    StageTemplate,
)
from backend.projects.models import Meeting, Project, ProjectDetail, ProjectSlug, ProjectStage
from backend.settings import Settings
from backend.tenancy.models import Tenant, TenantDomain

SAO_PAULO = timezone(timedelta(hours=-3))
# Fictional projects in Brazilian Portuguese (AGENTS.md), covering the edge cases
# the client page must handle: long names and accents, a draft, a project without
# stages, a completed password-protected one, a changed address, an office-written
# stage, past and upcoming meetings. The project password is "demo-senha".
PROJECTS = {
    "alinea": [
        {
            "slug": "casa-jardim",
            "name": "Casa Jardim",
            "client": "Família Oliveira",
            "template": StageTemplate.STANDARD,
            "status": ProjectStatus.ACTIVE,
            "current": 3,
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
            "notes": {2: "Briefing aprovado. Seguimos para os estudos preliminares."},
            "meetings": [(-14, "Aprovação do briefing"), (6, "Apresentação do layout")],
        },
        {
            "slug": "apartamento-atlantico",
            "old_slugs": ["apto-atlantico"],
            "name": "Apartamento Atlântico — Copacabana",
            "client": "Clara Martins e Rafael Nogueira de Albuquerque",
            "template": StageTemplate.INTERIORS,
            "status": ProjectStatus.ACTIVE,
            "current": 3,
            "description": "Reforma completa de um apartamento de frente para o mar.",
            "details": {
                DetailKey.LOCATION: "Rio de Janeiro — RJ",
                DetailKey.BUILT_AREA: Decimal("148.5"),
                DetailKey.EXPECTED_DELIVERY: date(2026, 12, 18),
            },
            "custom_stage": ("Aprovação no condomínio", "Envio do projeto à administração."),
        },
        {
            "slug": "casa-das-oliveiras",
            "name": "Casa das Oliveiras",
            "client": "Família Almeida",
            "template": StageTemplate.EMPTY,
            "status": ProjectStatus.DRAFT,
        },
        {
            "slug": "refugio-da-mantiqueira",
            "name": "Refúgio da Mantiqueira",
            "client": "Helena e André",
            "template": StageTemplate.STANDARD,
            "status": ProjectStatus.COMPLETED,
            "current": 7,
            "password": "demo-senha",
        },
    ],
    "norte": [
        # The same slug as an Alinea project: slugs are per office.
        {
            "slug": "casa-jardim",
            "name": "Casa Jardim (Norte)",
            "client": "Família Rocha",
            "template": StageTemplate.STANDARD,
            "status": ProjectStatus.ACTIVE,
            "current": 1,
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
    project = Project(
        **owned,
        name=spec["name"],
        client_name=spec["client"],
        project_type=TEMPLATE_PROJECT_TYPE[spec["template"]],
        stage_template=spec["template"],
        status=spec["status"],
        description=spec.get("description", ""),
        current_position=spec.get("current"),
        access_mode=AccessMode.PASSWORD if password else AccessMode.PUBLIC,
        password_hash=await hash_password(password) if password else None,
    )
    session.add(project)
    await session.flush()
    owned["project_id"] = project.id
    for old in spec.get("old_slugs", []):
        session.add(ProjectSlug(**owned, slug=old, is_current=False))
    session.add(ProjectSlug(**owned, slug=spec["slug"]))
    stages = list(TEMPLATE_STAGES[spec["template"]])
    notes = spec.get("notes", {})
    for position, key in enumerate(stages, start=1):
        note = notes.get(position, "")
        session.add(
            ProjectStage(
                **owned,
                position=position,
                builtin_key=key,
                notes=note,
                notes_updated_at=datetime.now(SAO_PAULO) if note else None,
            )
        )
    if custom := spec.get("custom_stage"):
        title, about = custom
        session.add(ProjectStage(**owned, position=len(stages) + 1, title=title, about=about))
    for position, (key, value) in enumerate(spec.get("details", {}).items(), start=1):
        column = (
            "value_number"
            if isinstance(value, Decimal)
            else "value_date"
            if isinstance(value, date)
            else "value_text"
        )
        session.add(ProjectDetail(**owned, key=key, position=position, **{column: value}))
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
