"""A fifth project type, Visualização Arquitetônica (A27, Fabio, 2 Nov 2026;
without "Projeto de", so its name fits the creation form's button on one line),
with four stages of its own after the 11 building ones: Documentação,
Entrega Prévia, Revisões and Entrega Final. Briefing is shared. All five are its
usual stages (ticked at creation), each in this type's words, as Alinea wrote
them for its proposals (Fabio, 2 Nov 2026).

Reference data only: no schema change, and the app already reads these tables.

Downgrade removes the rows; a project of this type, or with one of these stages,
stops it (they reference them), as it should.

Revision: 0045
Previous: 0044
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0045"
down_revision: str | None = "0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TYPE = "visualization"
TYPE_LABELS = {
    "pt-BR": "Visualização Arquitetônica",
    "en": "Architectural visualization",
}

# Its usual stages, each in this type's words: Briefing (shared), then its own.
TYPE_STAGES = {
    "briefing": (
        (
            "Levantamento das necessidades, expectativas, referências e preferências do "
            "contratante, incluindo as ideias e o conceito desejado para o projeto. Também "
            "compreende a análise das características do imóvel e das informações fornecidas "
            "para orientar o desenvolvimento das soluções arquitetônicas."
        ),
        (
            "Gathering the client's needs, expectations, references and preferences, "
            "including the ideas and concept wanted for the project. Also covers analysing "
            "the property's characteristics and the information provided, to guide the "
            "architectural solutions."
        ),
    ),
    "preview_delivery": (
        (
            "Apresentação das soluções e estudos preliminares para análise e aprovação do "
            "contratante, conforme a etapa e o escopo contratados."
        ),
        (
            "Presentation of the solutions and preliminary studies for the client's review "
            "and approval, according to the stage and scope contracted."
        ),
    ),
    "documentation": (
        (
            "Arquivos e documentos necessários ao desenvolvimento e ao registro e elaboração "
            "do projeto, conforme as informações e definições estabelecidas."
        ),
        (
            "The files and documents needed to develop, record and prepare the project, "
            "according to the information and decisions established."
        ),
    ),
    "revisions": (
        (
            "Avaliação das considerações apresentadas pelo contratante e realização de "
            "ajustes e adequações nas soluções propostas."
        ),
        "Review of the client's comments and adjustments to the proposed solutions.",
    ),
    "final_delivery": (
        (
            "Conclusão e apresentação do projeto em sua versão definitiva, reunindo as "
            "soluções desenvolvidas, os ajustes realizados e as informações necessárias à sua "
            "compreensão e utilização."
        ),
        (
            "Completion and presentation of the project in its final version, bringing "
            "together the solutions developed, the adjustments made and the information "
            "needed to understand and use it."
        ),
    ),
}

# After the 11 building stages, in the order a visualization project lists them;
# only this type uses them, so their general text is the type's.
STAGES = [
    {"key": "documentation", "titles": {"pt-BR": "Documentação", "en": "Documentation"}},
    {"key": "preview_delivery", "titles": {"pt-BR": "Entrega Prévia", "en": "Preview Delivery"}},
    {"key": "revisions", "titles": {"pt-BR": "Revisões", "en": "Revisions"}},
    {"key": "final_delivery", "titles": {"pt-BR": "Entrega Final", "en": "Final Delivery"}},
]


def upgrade() -> None:
    project_types = sa.table(
        "project_types",
        sa.column("key", sa.Text()),
        sa.column("position", sa.Integer()),
        sa.column("labels", JSONB()),
    )
    op.bulk_insert(project_types, [{"key": TYPE, "position": 5, "labels": TYPE_LABELS}])
    stage_definitions = sa.table(
        "stage_definitions",
        sa.column("key", sa.Text()),
        sa.column("position", sa.Integer()),
        sa.column("titles", JSONB()),
        sa.column("about", JSONB()),
    )
    op.bulk_insert(
        stage_definitions,
        [
            {
                **stage,
                "position": n,
                "about": {
                    "pt-BR": TYPE_STAGES[stage["key"]][0],
                    "en": TYPE_STAGES[stage["key"]][1],
                },
            }
            for n, stage in enumerate(STAGES, start=12)
        ],
    )
    type_stages = sa.table(
        "project_type_stages",
        sa.column("project_type", sa.Text()),
        sa.column("stage_key", sa.Text()),
        sa.column("about", JSONB()),
    )
    op.bulk_insert(
        type_stages,
        [
            {"project_type": TYPE, "stage_key": key, "about": {"pt-BR": pt, "en": en}}
            for key, (pt, en) in TYPE_STAGES.items()
        ],
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM project_types WHERE key = '{TYPE}'")  # its type stages go too
    keys = ", ".join(f"'{stage['key']}'" for stage in STAGES)
    op.execute(f"DELETE FROM stage_definitions WHERE key IN ({keys})")
