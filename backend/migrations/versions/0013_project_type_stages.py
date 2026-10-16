"""Project types choose their usual stages (A27, revised 16 Oct 2026).

The 12 built-in stages written by Alinea's partners replace the old ones, in
one fixed order; `project_type_stages` lists each type's usual stages (ticked
when a project is created) with the type's own description of each. Stage
templates and the separate "what the client receives" texts are removed.

Projects made with the old stages were tests: they are deleted, with their
addresses, stages, details and meetings. Their Drive folders are not touched.

Downgrade restores the old tables and columns, empty: the old built-in rows
come back only by downgrading past 0008.

Revision: 0013
Previous: 0012
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LANGUAGES = "ARRAY['pt-BR', 'en']"

PROJECT_TYPE_LABELS = {
    "architecture": {"pt-BR": "Projeto Arquitetônico", "en": "Architecture project"},
    "interiors": {"pt-BR": "Projeto de Interiores", "en": "Interior design project"},
    "renovation": {"pt-BR": "Projeto de Reforma", "en": "Renovation project"},
    "landscaping": {"pt-BR": "Projeto de Paisagismo", "en": "Landscape project"},
}

# In the order every project lists them; `about` is the general description,
# used when a stage is chosen outside its type's usual list.
STAGES = [
    {
        "key": "briefing",
        "titles": {"pt-BR": "Briefing", "en": "Briefing"},
        "about": {
            "pt-BR": "Levantamento das necessidades, expectativas e orçamento do cliente.",
            "en": "The client's needs, expectations and budget.",
        },
    },
    {
        "key": "survey",
        "titles": {"pt-BR": "Levantamento", "en": "Survey"},
        "about": {
            "pt-BR": "Análise do local: medidas, legislação e condicionantes.",
            "en": "Study of the site: measurements, regulations and constraints.",
        },
    },
    {
        "key": "survey_assessment",
        "titles": {"pt-BR": "Levantamento e Diagnóstico", "en": "Survey and assessment"},
        "about": {
            "pt-BR": "Análise das condições existentes, estrutura e instalações.",
            "en": "Assessment of the existing conditions, structure and services.",
        },
    },
    {
        "key": "feasibility_study",
        "titles": {"pt-BR": "Estudo de Viabilidade", "en": "Feasibility study"},
        "about": {
            "pt-BR": "Avaliação das possibilidades técnicas, legais e financeiras.",
            "en": "Assessment of the technical, legal and financial options.",
        },
    },
    {
        "key": "preliminary_study",
        "titles": {"pt-BR": "Estudo Preliminar", "en": "Preliminary study"},
        "about": {
            "pt-BR": "Conceito, organização dos espaços e primeiras propostas.",
            "en": "Concept, layout of the spaces and first proposals.",
        },
    },
    {
        "key": "schematic_design",
        "titles": {"pt-BR": "Anteprojeto", "en": "Schematic design"},
        "about": {
            "pt-BR": "Desenvolvimento da proposta: plantas, materiais e soluções.",
            "en": "The proposal developed: plans, materials and solutions.",
        },
    },
    {
        "key": "permit_documents",
        "titles": {"pt-BR": "Projeto Legal", "en": "Permit documents"},
        "about": {
            "pt-BR": "Documentação para aprovação nos órgãos competentes, quando necessária.",
            "en": "Documents for approval by the authorities, when required.",
        },
    },
    {
        "key": "construction_documents",
        "titles": {"pt-BR": "Projeto Executivo", "en": "Construction documents"},
        "about": {
            "pt-BR": "Detalhamento técnico para execução da obra.",
            "en": "Technical drawings and details for construction.",
        },
    },
    {
        "key": "detailing",
        "titles": {"pt-BR": "Detalhamentos", "en": "Detailing"},
        "about": {
            "pt-BR": "Marcenaria, marmoraria, serralheria e demais elementos personalizados.",
            "en": "Joinery, stonework, metalwork and other custom elements.",
        },
    },
    {
        "key": "coordination",
        "titles": {"pt-BR": "Compatibilização", "en": "Coordination"},
        "about": {
            "pt-BR": "Integração com projetos complementares, como estrutural e instalações.",
            "en": "Coordination with the engineering projects, such as structure and services.",
        },
    },
    {
        "key": "complementary_projects",
        "titles": {"pt-BR": "Projetos Complementares", "en": "Complementary projects"},
        "about": {
            "pt-BR": "Projetos de apoio, como irrigação, drenagem e iluminação, conforme o escopo.",
            "en": "Supporting projects such as irrigation, drainage and lighting, as scoped.",
        },
    },
    {
        "key": "specifications",
        "titles": {"pt-BR": "Especificações", "en": "Specifications"},
        "about": {
            "pt-BR": "Relação de materiais, mobiliário, equipamentos e fornecedores.",
            "en": "List of materials, furniture, equipment and suppliers.",
        },
    },
]

# Each type's usual stages, in the words of Alinea's partners (16 Oct 2026).
TYPE_STAGES = {
    "architecture": {
        "briefing": (
            "Levantamento das necessidades, expectativas e orçamento do cliente.",
            "The client's needs, expectations and budget.",
        ),
        "survey": (
            "Análise do terreno, medidas, legislação e condicionantes.",
            "Study of the plot, measurements, regulations and constraints.",
        ),
        "preliminary_study": (
            "Conceito arquitetônico, implantação, layout e volumetria.",
            "Architectural concept, siting, layout and massing.",
        ),
        "schematic_design": (
            "Desenvolvimento das plantas, fachadas, cortes e soluções arquitetônicas.",
            "Plans, elevations, sections and architectural solutions developed.",
        ),
        "permit_documents": (
            "Documentação para aprovação nos órgãos competentes, quando necessária.",
            "Documents for approval by the authorities, when required.",
        ),
        "construction_documents": (
            "Detalhamento técnico para execução da obra.",
            "Technical drawings and details for construction.",
        ),
        "coordination": (
            "Integração com projetos complementares, como estrutural e instalações.",
            "Coordination with the engineering projects, such as structure and services.",
        ),
    },
    "interiors": {
        "briefing": (
            "Identificação das necessidades, estilo de vida e preferências do cliente.",
            "The client's needs, way of life and preferences.",
        ),
        "survey": (
            "Medições e análise dos ambientes existentes ou projetados.",
            "Measurements and study of the existing or planned rooms.",
        ),
        "preliminary_study": (
            "Conceito, layout, referências e proposta estética.",
            "Concept, layout, references and the look proposed.",
        ),
        "schematic_design": (
            "Definição de materiais, mobiliário, iluminação e acabamentos.",
            "Materials, furniture, lighting and finishes chosen.",
        ),
        "construction_documents": (
            "Plantas técnicas, iluminação, elétrica, forro, revestimentos e paginações.",
            "Technical plans: lighting, electrical, ceilings, finishes and tiling layouts.",
        ),
        "detailing": (
            "Marcenaria, marmoraria, serralheria e demais elementos personalizados.",
            "Joinery, stonework, metalwork and other custom elements.",
        ),
        "specifications": (
            "Relação de mobiliário, equipamentos, materiais e fornecedores.",
            "List of furniture, equipment, materials and suppliers.",
        ),
    },
    "renovation": {
        "briefing": (
            "Identificação dos objetivos, necessidades e orçamento da reforma.",
            "The renovation's goals, needs and budget.",
        ),
        "survey_assessment": (
            "Análise das condições existentes, estrutura e instalações.",
            "Assessment of the existing conditions, structure and services.",
        ),
        "feasibility_study": (
            "Avaliação das possibilidades técnicas, legais e financeiras.",
            "Assessment of the technical, legal and financial options.",
        ),
        "preliminary_study": (
            "Propostas de reorganização, alterações e melhorias dos espaços.",
            "Proposals to reorganise, change and improve the spaces.",
        ),
        "schematic_design": (
            "Definição das intervenções, materiais e soluções construtivas.",
            "The works, materials and building solutions defined.",
        ),
        "permit_documents": (
            "Aprovações e autorizações necessárias, quando aplicáveis.",
            "Approvals and permits required, when applicable.",
        ),
        "construction_documents": (
            "Plantas de demolição, construção, adequações e detalhamentos técnicos.",
            "Demolition, construction and adaptation plans, with technical details.",
        ),
        "coordination": (
            "Coordenação das intervenções com estrutura e instalações existentes.",
            "The works coordinated with the existing structure and services.",
        ),
    },
    "landscaping": {
        "briefing": (
            "Identificação das necessidades, usos e preferências do cliente.",
            "The client's needs, uses and preferences.",
        ),
        "survey": (
            "Análise do terreno, topografia, insolação, clima e vegetação existente.",
            "Study of the site, topography, sunlight, climate and existing vegetation.",
        ),
        "preliminary_study": (
            "Conceito paisagístico, setorização e organização dos espaços externos.",
            "Landscape concept, zoning and layout of the outdoor spaces.",
        ),
        "schematic_design": (
            "Definição de espécies vegetais, caminhos, jardins e elementos paisagísticos.",
            "Plant species, paths, gardens and landscape elements defined.",
        ),
        "construction_documents": (
            "Plantas de implantação, plantio, pisos, canteiros e detalhamentos.",
            "Site, planting, paving and bed plans, with details.",
        ),
        "complementary_projects": (
            "Irrigação, drenagem e iluminação externa, conforme o escopo.",
            "Irrigation, drainage and outdoor lighting, as scoped.",
        ),
        "specifications": (
            "Listagem de espécies, quantitativos, materiais e orientações de implantação.",
            "Species, quantities, materials and planting guidance.",
        ),
    },
}


def _texts(column: str, table: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(
        f"jsonb_typeof({column}) = 'object' AND {column} ?& {LANGUAGES}",
        name=op.f(f"ck_{table}_{column}_in_every_language"),
    )


def upgrade() -> None:
    # The old stages' projects were tests (Fabio, 16 Oct 2026). The migration
    # login owns the tables but is bound by forced isolation, so lift it while
    # deleting every office's rows; the children go by ON DELETE CASCADE.
    op.execute("ALTER TABLE projects NO FORCE ROW LEVEL SECURITY")
    op.execute("DELETE FROM projects")
    op.execute("ALTER TABLE projects FORCE ROW LEVEL SECURITY")

    op.drop_constraint(op.f("fk_projects_stage_template"), "projects", type_="foreignkey")
    op.drop_column("projects", "stage_template")
    op.drop_table("stage_template_stages")
    op.drop_table("stage_templates")

    # Built-in stages: one description each, in a fixed order.
    op.drop_constraint(
        op.f("ck_project_stages_builtin_texts_translated"), "project_stages", type_="check"
    )
    op.drop_column("project_stages", "deliverables")
    op.create_check_constraint(
        op.f("ck_project_stages_builtin_texts_translated"),
        "project_stages",
        "builtin_key IS NULL OR about IS NULL",
    )
    op.execute("DELETE FROM stage_definitions")
    op.drop_column("stage_definitions", "deliverables")
    op.add_column("stage_definitions", sa.Column("position", sa.Integer(), nullable=False))
    stage_definitions = sa.table(
        "stage_definitions",
        sa.column("key", sa.Text()),
        sa.column("position", sa.Integer()),
        sa.column("titles", JSONB()),
        sa.column("about", JSONB()),
    )
    op.bulk_insert(
        stage_definitions,
        [{**stage, "position": n} for n, stage in enumerate(STAGES, start=1)],
    )

    type_stages = op.create_table(
        "project_type_stages",
        sa.Column(
            "project_type",
            sa.Text(),
            sa.ForeignKey("project_types.key", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "stage_key",
            sa.Text(),
            sa.ForeignKey("stage_definitions.key", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("about", JSONB(), nullable=False),
        _texts("about", "project_type_stages"),
    )
    op.bulk_insert(
        type_stages,
        [
            {"project_type": kind, "stage_key": key, "about": {"pt-BR": pt, "en": en}}
            for kind, stages in TYPE_STAGES.items()
            for key, (pt, en) in stages.items()
        ],
    )
    for key, labels in PROJECT_TYPE_LABELS.items():
        op.execute(
            sa.text(
                "UPDATE project_types SET labels = CAST(:labels AS jsonb) WHERE key = :key"
            ).bindparams(labels=json.dumps(labels, ensure_ascii=False), key=key)
        )

    op.execute(
        """
        DO $$
        BEGIN
            EXECUTE format(
                'GRANT SELECT ON project_type_stages TO %I', current_database() || '_app'
            );
        END $$
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE projects NO FORCE ROW LEVEL SECURITY")
    op.execute("DELETE FROM projects")
    op.execute("ALTER TABLE projects FORCE ROW LEVEL SECURITY")
    op.drop_table("project_type_stages")
    op.execute("DELETE FROM stage_definitions")
    op.drop_column("stage_definitions", "position")
    op.add_column("stage_definitions", sa.Column("deliverables", JSONB(), nullable=False))
    op.create_check_constraint(
        op.f("ck_stage_definitions_deliverables_in_every_language"),
        "stage_definitions",
        f"jsonb_typeof(deliverables) = 'object' AND deliverables ?& {LANGUAGES}",
    )
    op.drop_constraint(
        op.f("ck_project_stages_builtin_texts_translated"), "project_stages", type_="check"
    )
    op.add_column("project_stages", sa.Column("deliverables", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_project_stages_builtin_texts_translated"),
        "project_stages",
        "builtin_key IS NULL OR (about IS NULL AND deliverables IS NULL)",
    )
    op.create_table(
        "stage_templates",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("labels", JSONB(), nullable=False),
        sa.Column(
            "default_project_type", sa.Text(), sa.ForeignKey("project_types.key"), nullable=False
        ),
        _texts("labels", "stage_templates"),
    )
    op.create_table(
        "stage_template_stages",
        sa.Column(
            "template_key",
            sa.Text(),
            sa.ForeignKey("stage_templates.key", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column("stage_key", sa.Text(), sa.ForeignKey("stage_definitions.key"), nullable=False),
    )
    op.execute(
        """
        DO $$
        BEGIN
            EXECUTE format(
                'GRANT SELECT ON stage_templates, stage_template_stages TO %I',
                current_database() || '_app'
            );
        END $$
        """
    )
    op.add_column("projects", sa.Column("stage_template", sa.Text(), nullable=False))
    op.create_foreign_key(
        op.f("fk_projects_stage_template"),
        "projects",
        "stage_templates",
        ["stage_template"],
        ["key"],
    )
