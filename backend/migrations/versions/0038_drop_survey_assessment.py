"""One survey stage: "Levantamento e Diagnóstico" goes, "Levantamento" covers it
(Fabio, 26 Oct 2026; A27 now lists 11 built-in stages).

Reforma's usual stages take "Levantamento", keeping Reforma's own description of
it. Projects that had "Levantamento e Diagnóstico" now have "Levantamento" in the
same place, notes and folder unchanged; a project that already had both keeps the
second as its own stage, titled as before. Stages after it move up one in the
built-in order. Every office's projects are updated, so the forced isolation
policy is lifted for that update (see snippets.py).

Revision: 0038
Previous: 0037
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0038"
down_revision: str | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO project_type_stages (project_type, stage_key, about)
        SELECT project_type, 'survey', about FROM project_type_stages
        WHERE stage_key = 'survey_assessment'
        ON CONFLICT DO NOTHING
        """
    )
    op.execute("ALTER TABLE project_stages NO FORCE ROW LEVEL SECURITY")  # every office's
    # Already has "Levantamento": keep this one as the office's own stage.
    op.execute(
        """
        UPDATE project_stages s
        SET builtin_key = NULL, title = d.titles ->> t.locale, about = d.about ->> t.locale
        FROM stage_definitions d, tenants t
        WHERE s.builtin_key = 'survey_assessment' AND d.key = 'survey_assessment'
          AND t.id = s.tenant_id
          AND EXISTS (
              SELECT 1 FROM project_stages o
              WHERE o.project_id = s.project_id AND o.builtin_key = 'survey'
          )
        """
    )
    op.execute(
        "UPDATE project_stages SET builtin_key = 'survey' WHERE builtin_key = 'survey_assessment'"
    )
    op.execute("ALTER TABLE project_stages FORCE ROW LEVEL SECURITY")
    op.execute("DELETE FROM project_type_stages WHERE stage_key = 'survey_assessment'")
    op.execute(
        """
        UPDATE stage_definitions SET position = position - 1
        WHERE position > (SELECT position FROM stage_definitions WHERE key = 'survey_assessment')
        """
    )
    op.execute("DELETE FROM stage_definitions WHERE key = 'survey_assessment'")


def downgrade() -> None:
    # The definition and Reforma's list come back; projects keep "Levantamento".
    op.execute(
        """
        UPDATE stage_definitions SET position = position + 1
        WHERE position > (SELECT position FROM stage_definitions WHERE key = 'survey')
        """
    )
    op.execute(
        """
        INSERT INTO stage_definitions (key, position, titles, about)
        SELECT 'survey_assessment', position + 1,
               '{"pt-BR": "Levantamento e Diagnóstico", "en": "Survey and assessment"}',
               '{"pt-BR": "Análise das condições existentes, estrutura e instalações.",
                 "en": "Assessment of the existing conditions, structure and services."}'
        FROM stage_definitions WHERE key = 'survey'
        """
    )
    op.execute(
        """
        UPDATE project_type_stages SET stage_key = 'survey_assessment'
        WHERE project_type = 'renovation' AND stage_key = 'survey'
        """
    )
