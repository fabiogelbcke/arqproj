"""A fifth project type, Visualização Arquitetônica (A27, Fabio, 2 Nov 2026;
without "Projeto de", so its name fits the creation form's button on one line),
with five stages of its own after the 11 building ones: Entrega Prévia,
Documentação, Revisões, Entrega Final and Pós-Produção. Briefing is shared.
Its usual stages (ticked at creation) are all but Revisões and Pós-Produção.

The texts are drafts for Alinea's partners to confirm, like 0013's. Reference
data only: no schema change, and the app already reads these tables.

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

# After the 11 building stages, in the order a visualization project lists them.
STAGES = [
    {
        "key": "preview_delivery",
        "titles": {"pt-BR": "Entrega Prévia", "en": "Preview Delivery"},
        "about": {
            "pt-BR": (
                "Primeiras imagens para o cliente avaliar enquadramentos, materiais e iluminação."
            ),
            "en": "First images for the client to review framing, materials and lighting.",
        },
    },
    {
        "key": "documentation",
        "titles": {"pt-BR": "Documentação", "en": "Documentation"},
        "about": {
            "pt-BR": (
                "Arquivos do projeto, referências e especificações de materiais usados nas imagens."
            ),
            "en": "The project files, references and material specifications the images use.",
        },
    },
    {
        "key": "revisions",
        "titles": {"pt-BR": "Revisões", "en": "Revisions"},
        "about": {
            "pt-BR": "Ajustes nas imagens a partir dos comentários do cliente.",
            "en": "Changes to the images from the client's comments.",
        },
    },
    {
        "key": "final_delivery",
        "titles": {"pt-BR": "Entrega Final", "en": "Final Delivery"},
        "about": {
            "pt-BR": "Imagens finais em alta resolução.",
            "en": "The final images in high resolution.",
        },
    },
    {
        "key": "post_production",
        "titles": {"pt-BR": "Pós-Produção", "en": "Post-Production"},
        "about": {
            "pt-BR": "Tratamento de cor, luz e composição, e versões das imagens para cada uso.",
            "en": (
                "Colour, light and composition retouching, and versions of the images for each use."
            ),
        },
    },
]

# Its usual stages, each in this type's words.
TYPE_STAGES = {
    "briefing": (
        "Objetivo das imagens, vistas desejadas, referências e prazo.",
        "What the images are for, the views wanted, references and deadline.",
    ),
    "preview_delivery": (
        "Primeiras imagens para o cliente avaliar enquadramentos, materiais e iluminação.",
        "First images for the client to review framing, materials and lighting.",
    ),
    "documentation": (
        "Arquivos do projeto, referências e especificações de materiais usados nas imagens.",
        "The project files, references and material specifications the images use.",
    ),
    "final_delivery": (
        "Imagens finais em alta resolução.",
        "The final images in high resolution.",
    ),
}


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
        [{**stage, "position": n} for n, stage in enumerate(STAGES, start=12)],
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
