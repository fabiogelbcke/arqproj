"""Built-in content as reference tables: project types, detail types, stage
definitions and stage templates (with their stages). Foreign keys replace the
CHECKs on the columns that use them; a detail row also stores its value type.

Content the app only displays lives in the database (texts per language in each
row); the code keeps enums naming the built-in keys, kept in step by a test.

Revision: 0008
Previous: 0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Every text column holds one entry per supported language.
LANGUAGES = "ARRAY['pt-BR', 'en']"

PROJECT_TYPES = [
    {
        "key": "architecture",
        "position": 1,
        "labels": {"pt-BR": "Projeto Arquitetônico", "en": "Architecture"},
    },
    {
        "key": "interiors",
        "position": 2,
        "labels": {"pt-BR": "Projeto de Interiores", "en": "Interior design"},
    },
    {"key": "renovation", "position": 3, "labels": {"pt-BR": "Reforma", "en": "Renovation"}},
    {"key": "landscaping", "position": 4, "labels": {"pt-BR": "Paisagismo", "en": "Landscaping"}},
]

DETAIL_TYPES = [
    {
        "key": "client",
        "value_type": "text",
        "position": 1,
        "labels": {"pt-BR": "Cliente", "en": "Client"},
    },
    {
        "key": "location",
        "value_type": "text",
        "position": 2,
        "labels": {"pt-BR": "Localização", "en": "Location"},
    },
    {
        "key": "site_area",
        "value_type": "area",
        "position": 3,
        "labels": {"pt-BR": "Área do terreno", "en": "Site area"},
    },
    {
        "key": "built_area",
        "value_type": "area",
        "position": 4,
        "labels": {"pt-BR": "Área construída", "en": "Built area"},
    },
    {
        "key": "start_date",
        "value_type": "date",
        "position": 5,
        "labels": {"pt-BR": "Início", "en": "Start"},
    },
    {
        "key": "expected_delivery",
        "value_type": "date",
        "position": 6,
        "labels": {"pt-BR": "Previsão de entrega", "en": "Expected delivery"},
    },
    {
        "key": "responsible",
        "value_type": "text",
        "position": 7,
        "labels": {"pt-BR": "Responsável", "en": "Lead architect"},
    },
]

STAGE_DEFINITIONS = [
    {
        "key": "proposal",
        "titles": {"pt-BR": "Proposta", "en": "Proposal"},
        "about": {
            "pt-BR": "Escopo, condições e planejamento do projeto.",
            "en": "Scope, terms and planning of the project.",
        },
        "deliverables": {
            "pt-BR": "Proposta de serviços, etapas, prazos e valores previstos.",
            "en": "Service proposal with stages, timeline and fees.",
        },
    },
    {
        "key": "briefing_survey",
        "titles": {"pt-BR": "Briefing e Levantamento", "en": "Brief and survey"},
        "about": {
            "pt-BR": "Entendimento das necessidades e das características do espaço.",
            "en": "Understanding your needs and the characteristics of the space.",
        },
        "deliverables": {
            "pt-BR": "Programa de necessidades, levantamento e registros do local.",
            "en": "Requirements, site survey and records.",
        },
    },
    {
        "key": "preliminary_studies",
        "titles": {
            "pt-BR": "Estudos Preliminares / Anteprojeto",
            "en": "Preliminary studies / Schematic design",
        },
        "about": {
            "pt-BR": "Organização dos ambientes e definição do conceito.",
            "en": "Arranging the spaces and defining the concept.",
        },
        "deliverables": {
            "pt-BR": "Plantas, estudos de implantação e soluções preliminares.",
            "en": "Plans, site studies and preliminary solutions.",
        },
    },
    {
        "key": "model_3d",
        "titles": {"pt-BR": "Projeto 3D", "en": "3D design"},
        "about": {
            "pt-BR": "Visualização dos espaços, materiais e volumes.",
            "en": "Seeing the spaces, materials and volumes.",
        },
        "deliverables": {
            "pt-BR": "Perspectivas e imagens do projeto.",
            "en": "Perspectives and images of the project.",
        },
    },
    {
        "key": "construction_documents",
        "titles": {"pt-BR": "Projeto Executivo", "en": "Construction documents"},
        "about": {
            "pt-BR": "Detalhamento técnico das soluções aprovadas.",
            "en": "Technical detailing of the approved solutions.",
        },
        "deliverables": {
            "pt-BR": "Desenhos e especificações para orientar a execução.",
            "en": "Drawings and specifications to guide construction.",
        },
    },
    {
        "key": "final_delivery",
        "titles": {"pt-BR": "Entrega Final", "en": "Final delivery"},
        "about": {
            "pt-BR": "Organização da documentação final do projeto.",
            "en": "Organizing the project's final documentation.",
        },
        "deliverables": {
            "pt-BR": "Conjunto final de desenhos e arquivos.",
            "en": "Final set of drawings and files.",
        },
    },
    {
        "key": "extra_services",
        "titles": {"pt-BR": "Serviços extras", "en": "Additional services"},
        "about": {
            "pt-BR": "Acompanhamento dos serviços complementares contratados.",
            "en": "Following up the additional services commissioned.",
        },
        "deliverables": {
            "pt-BR": "Documentos e orientações conforme o escopo combinado.",
            "en": "Documents and guidance within the agreed scope.",
        },
    },
    {
        "key": "briefing",
        "titles": {"pt-BR": "Briefing", "en": "Brief"},
        "about": {
            "pt-BR": "Conversamos sobre usos, prioridades e expectativas.",
            "en": "We talk about uses, priorities and expectations.",
        },
        "deliverables": {
            "pt-BR": "Programa de necessidades e referências.",
            "en": "Requirements and references.",
        },
    },
    {
        "key": "layout",
        "titles": {"pt-BR": "Layout", "en": "Layout"},
        "about": {
            "pt-BR": "Distribuição dos ambientes, mobiliário e circulação.",
            "en": "Arranging rooms, furniture and circulation.",
        },
        "deliverables": {
            "pt-BR": "Plantas de layout para análise e alinhamento.",
            "en": "Layout plans to review and agree on.",
        },
    },
    {
        "key": "detailing",
        "titles": {"pt-BR": "Detalhamento", "en": "Detailing"},
        "about": {
            "pt-BR": "Definição dos elementos e soluções de interiores.",
            "en": "Defining the interior elements and solutions.",
        },
        "deliverables": {
            "pt-BR": "Detalhes de marcenaria, acabamentos e instalações previstas.",
            "en": "Joinery, finishes and planned installations in detail.",
        },
    },
]

STAGE_TEMPLATES = [
    {
        "key": "standard",
        "position": 1,
        "labels": {"pt-BR": "Padrão", "en": "Standard"},
        "default_project_type": "architecture",
    },
    {
        "key": "interiors",
        "position": 2,
        "labels": {"pt-BR": "Interiores", "en": "Interiors"},
        "default_project_type": "interiors",
    },
    {
        "key": "empty",
        "position": 3,
        "labels": {"pt-BR": "Sem etapas", "en": "No stages"},
        "default_project_type": "architecture",
    },
]

TEMPLATE_STAGES = [
    {"template_key": "standard", "position": 1, "stage_key": "proposal"},
    {"template_key": "standard", "position": 2, "stage_key": "briefing_survey"},
    {"template_key": "standard", "position": 3, "stage_key": "preliminary_studies"},
    {"template_key": "standard", "position": 4, "stage_key": "model_3d"},
    {"template_key": "standard", "position": 5, "stage_key": "construction_documents"},
    {"template_key": "standard", "position": 6, "stage_key": "final_delivery"},
    {"template_key": "standard", "position": 7, "stage_key": "extra_services"},
    {"template_key": "interiors", "position": 1, "stage_key": "proposal"},
    {"template_key": "interiors", "position": 2, "stage_key": "briefing"},
    {"template_key": "interiors", "position": 3, "stage_key": "layout"},
    {"template_key": "interiors", "position": 4, "stage_key": "model_3d"},
    {"template_key": "interiors", "position": 5, "stage_key": "detailing"},
    {"template_key": "interiors", "position": 6, "stage_key": "final_delivery"},
]


def _texts(column: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(
        f"jsonb_typeof({column}) = 'object' AND {column} ?& {LANGUAGES}",
        name=f"{column}_in_every_language",
    )


def upgrade() -> None:
    project_types = op.create_table(
        "project_types",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("labels", JSONB(), nullable=False),
        _texts("labels"),
    )
    detail_types = op.create_table(
        "detail_types",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("value_type", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("labels", JSONB(), nullable=False),
        sa.CheckConstraint("value_type IN ('text', 'area', 'date')", name="value_type_known"),
        _texts("labels"),
        # Lets a detail row reference (key, value_type): its value type is the type's.
        sa.UniqueConstraint("key", "value_type", name=op.f("uq_detail_types_key_value_type")),
    )
    stage_definitions = op.create_table(
        "stage_definitions",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("titles", JSONB(), nullable=False),
        sa.Column("about", JSONB(), nullable=False),
        sa.Column("deliverables", JSONB(), nullable=False),
        _texts("titles"),
        _texts("about"),
        _texts("deliverables"),
    )
    stage_templates = op.create_table(
        "stage_templates",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("labels", JSONB(), nullable=False),
        sa.Column(
            "default_project_type", sa.Text(), sa.ForeignKey("project_types.key"), nullable=False
        ),
        _texts("labels"),
    )
    template_stages = op.create_table(
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
    op.bulk_insert(project_types, PROJECT_TYPES)
    op.bulk_insert(detail_types, DETAIL_TYPES)
    op.bulk_insert(stage_definitions, STAGE_DEFINITIONS)
    op.bulk_insert(stage_templates, STAGE_TEMPLATES)
    op.bulk_insert(template_stages, TEMPLATE_STAGES)

    # Foreign keys instead of the lists the code used to check against.
    op.drop_constraint(op.f("ck_projects_project_type_known"), "projects", type_="check")
    op.drop_constraint(op.f("ck_projects_stage_template_known"), "projects", type_="check")
    op.create_foreign_key(
        op.f("fk_projects_project_type"), "projects", "project_types", ["project_type"], ["key"]
    )
    op.create_foreign_key(
        op.f("fk_projects_stage_template"),
        "projects",
        "stage_templates",
        ["stage_template"],
        ["key"],
    )
    op.drop_constraint(op.f("ck_project_stages_builtin_key_known"), "project_stages", type_="check")
    op.create_foreign_key(
        op.f("fk_project_stages_builtin_key"),
        "project_stages",
        "stage_definitions",
        ["builtin_key"],
        ["key"],
    )

    # A detail row carries its value type, so the database alone guarantees an
    # area is a number and a date is a date.
    op.drop_constraint(op.f("ck_project_details_key_known"), "project_details", type_="check")
    op.drop_constraint(
        op.f("ck_project_details_value_matches_type"), "project_details", type_="check"
    )
    op.add_column("project_details", sa.Column("value_type", sa.Text(), nullable=True))
    # Existing rows of every office: on Cloud SQL the migration login owns the
    # table but is no superuser, so the forced tenant policy would hide them all.
    # Lifted for this one update, inside this transaction, then restored.
    op.execute("ALTER TABLE project_details NO FORCE ROW LEVEL SECURITY")
    op.execute(
        "UPDATE project_details d SET value_type = t.value_type "
        "FROM detail_types t WHERE t.key = d.key"
    )
    op.execute("ALTER TABLE project_details FORCE ROW LEVEL SECURITY")
    op.alter_column("project_details", "value_type", nullable=False)
    op.create_check_constraint(
        op.f("ck_project_details_value_type_known"),
        "project_details",
        "value_type IN ('text', 'area', 'date')",
    )
    op.create_foreign_key(
        op.f("fk_project_details_detail_type"),
        "project_details",
        "detail_types",
        ["key", "value_type"],
        ["key", "value_type"],
    )
    op.create_check_constraint(
        op.f("ck_project_details_value_matches_type"),
        "project_details",
        "(value_type = 'text' AND value_text IS NOT NULL "
        "AND value_number IS NULL AND value_date IS NULL) OR "
        "(value_type = 'area' AND value_text IS NULL "
        "AND value_number IS NOT NULL AND value_date IS NULL) OR "
        "(value_type = 'date' AND value_text IS NULL "
        "AND value_number IS NULL AND value_date IS NOT NULL)",
    )

    # Read by the app; changed only by migrations (offices' own rows come later).
    op.execute(
        """
        DO $$
        BEGIN
            EXECUTE format(
                'GRANT SELECT ON project_types, detail_types, stage_definitions, '
                'stage_templates, stage_template_stages TO %I',
                current_database() || '_app'
            );
        END $$
        """
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_project_details_value_matches_type"), "project_details", type_="check"
    )
    op.drop_constraint(
        op.f("fk_project_details_detail_type"), "project_details", type_="foreignkey"
    )
    op.drop_constraint(
        op.f("ck_project_details_value_type_known"), "project_details", type_="check"
    )
    op.drop_column("project_details", "value_type")
    op.drop_constraint(op.f("fk_project_stages_builtin_key"), "project_stages", type_="foreignkey")
    op.drop_constraint(op.f("fk_projects_stage_template"), "projects", type_="foreignkey")
    op.drop_constraint(op.f("fk_projects_project_type"), "projects", type_="foreignkey")
    for table in (
        "stage_template_stages",
        "stage_templates",
        "stage_definitions",
        "detail_types",
        "project_types",
    ):
        op.drop_table(table)
    # The CHECKs this replaced come back from 0006's lists.
    op.create_check_constraint(
        op.f("ck_projects_project_type_known"),
        "projects",
        "project_type IN ('architecture', 'interiors', 'renovation', 'landscaping')",
    )
    op.create_check_constraint(
        op.f("ck_projects_stage_template_known"),
        "projects",
        "stage_template IN ('standard', 'interiors', 'empty')",
    )
    op.create_check_constraint(
        op.f("ck_project_stages_builtin_key_known"),
        "project_stages",
        "builtin_key IN ({})".format(", ".join(f"'{d['key']}'" for d in STAGE_DEFINITIONS)),
    )
    op.create_check_constraint(
        op.f("ck_project_details_key_known"),
        "project_details",
        "key IN ({})".format(", ".join(f"'{d['key']}'" for d in DETAIL_TYPES)),
    )
    op.create_check_constraint(
        op.f("ck_project_details_value_matches_type"),
        "project_details",
        (
            "(key IN ('client', 'location', 'responsible') "
            "AND value_text IS NOT NULL AND value_number IS NULL AND value_date IS NULL) OR "
            "(key IN ('site_area', 'built_area') "
            "AND value_text IS NULL AND value_number IS NOT NULL AND value_date IS NULL) OR "
            "(key IN ('start_date', 'expected_delivery') "
            "AND value_text IS NULL AND value_number IS NULL AND value_date IS NOT NULL)"
        ),
    )
