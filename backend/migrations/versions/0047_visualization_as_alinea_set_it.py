"""Visualização Arquitetônica as Alinea set it (A27, Fabio, 2–3 Nov 2026), on
databases that already ran 0045: no Pós-Produção; its stages in the order
Briefing, Documentação, Entrega Prévia, Revisões, Entrega Final, all five ticked at
creation, each described in the words Alinea uses in its proposals. Its own four
stages are only its, so their general description is the same text.

A project that had Pós-Produção keeps it as the office's own stage, titled and
described as before, notes and folder unchanged (as 0038 did). Every office's
projects are updated, so the forced isolation policy is lifted for that update
(see snippets.py).

Downgrade brings Pós-Produção back last, unticked, puts Entrega Prévia first
again and unticks Revisões; the texts stay Alinea's.

Revision: 0047
Previous: 0046
"""

import json
from collections.abc import Sequence

from alembic import op

revision: str = "0047"
down_revision: str | None = "0046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TYPE = "visualization"

# Its stages in order, each in this type's words: Briefing (shared), then its own.
TEXTS = {
    "briefing": (
        (
            "Levantamento das necessidades, expectativas, referências e preferências do "
            "contratante, incluindo as ideias e o conceito desejado para o projeto. Também "
            "compreende a análise das características do imóvel e das informações "
            "fornecidas para orientar o desenvolvimento das soluções arquitetônicas."
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
            "Arquivos e documentos necessários ao desenvolvimento e ao registro e "
            "elaboração do projeto, conforme as informações e definições estabelecidas."
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
            "soluções desenvolvidas, os ajustes realizados e as informações necessárias à "
            "sua compreensão e utilização."
        ),
        (
            "Completion and presentation of the project in its final version, bringing "
            "together the solutions developed, the adjustments made and the information "
            "needed to understand and use it."
        ),
    ),
}
ORDER = {"documentation": 12, "preview_delivery": 13, "revisions": 14, "final_delivery": 15}


# Pós-Produção as 0045 made it, for a downgrade.
POST_PRODUCTION_TITLES = {"pt-BR": "Pós-Produção", "en": "Post-Production"}
POST_PRODUCTION_ABOUT = {
    "pt-BR": "Tratamento de cor, luz e composição, e versões das imagens para cada uso.",
    "en": "Colour, light and composition retouching, and versions of the images for each use.",
}


def _json(texts: dict[str, str]) -> str:
    """As an SQL string literal's contents."""
    return json.dumps(texts, ensure_ascii=False).replace("'", "''")


def _about(key: str) -> str:
    pt, en = TEXTS[key]
    return _json({"pt-BR": pt, "en": en})


def upgrade() -> None:
    op.execute("ALTER TABLE project_stages NO FORCE ROW LEVEL SECURITY")  # every office's
    op.execute(
        """
        UPDATE project_stages s
        SET builtin_key = NULL, title = d.titles ->> t.locale, about = d.about ->> t.locale
        FROM stage_definitions d, tenants t
        WHERE s.builtin_key = 'post_production' AND d.key = 'post_production'
          AND t.id = s.tenant_id
        """
    )
    op.execute("ALTER TABLE project_stages FORCE ROW LEVEL SECURITY")
    op.execute("DELETE FROM project_type_stages WHERE stage_key = 'post_production'")
    op.execute("DELETE FROM stage_definitions WHERE key = 'post_production'")
    for key in TEXTS:
        op.execute(
            f"""
            INSERT INTO project_type_stages (project_type, stage_key, about)
            VALUES ('{TYPE}', '{key}', '{_about(key)}'::jsonb)
            ON CONFLICT (project_type, stage_key) DO UPDATE SET about = EXCLUDED.about
            """
        )
    for key, position in ORDER.items():
        op.execute(
            f"""
            UPDATE stage_definitions SET position = {position}, about = '{_about(key)}'::jsonb
            WHERE key = '{key}'
            """
        )


def downgrade() -> None:
    op.execute(
        "UPDATE stage_definitions SET position = 12 + (key = 'documentation')::int "
        "WHERE key IN ('preview_delivery', 'documentation')"
    )
    op.execute(
        f"""
        INSERT INTO stage_definitions (key, position, titles, about)
        VALUES ('post_production', 16, '{_json(POST_PRODUCTION_TITLES)}'::jsonb,
                '{_json(POST_PRODUCTION_ABOUT)}'::jsonb)
        """
    )
    op.execute(
        f"DELETE FROM project_type_stages WHERE project_type = '{TYPE}' AND stage_key = 'revisions'"
    )
