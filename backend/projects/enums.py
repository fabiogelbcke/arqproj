"""Fixed sets of values for projects (plan A26, A27).

Stored as text with a CHECK built from each enum. Their words live in the
translation catalogs (backend/i18n): project type, status, built-in stages and
details are shown translated; text an office writes is shown as typed.
"""

from __future__ import annotations

from enum import StrEnum


class ProjectStatus(StrEnum):
    DRAFT = "draft"  # Rascunho: staff only; the client page answers "not found"
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"  # still viewable; no new uploads or emails (plan section 22)


class AccessMode(StrEnum):
    PUBLIC = "public"
    PASSWORD = "password"


class ProjectType(StrEnum):
    ARCHITECTURE = "architecture"
    INTERIORS = "interiors"
    RENOVATION = "renovation"
    LANDSCAPING = "landscaping"


class BuiltinStage(StrEnum):
    PROPOSAL = "proposal"
    BRIEFING_SURVEY = "briefing_survey"
    PRELIMINARY_STUDIES = "preliminary_studies"
    MODEL_3D = "model_3d"
    CONSTRUCTION_DOCUMENTS = "construction_documents"
    FINAL_DELIVERY = "final_delivery"
    EXTRA_SERVICES = "extra_services"
    BRIEFING = "briefing"
    LAYOUT = "layout"
    DETAILING = "detailing"


class StageTemplate(StrEnum):
    STANDARD = "standard"  # Padrão
    INTERIORS = "interiors"
    EMPTY = "empty"


TEMPLATE_STAGES: dict[StageTemplate, tuple[BuiltinStage, ...]] = {
    StageTemplate.STANDARD: (
        BuiltinStage.PROPOSAL,
        BuiltinStage.BRIEFING_SURVEY,
        BuiltinStage.PRELIMINARY_STUDIES,
        BuiltinStage.MODEL_3D,
        BuiltinStage.CONSTRUCTION_DOCUMENTS,
        BuiltinStage.FINAL_DELIVERY,
        BuiltinStage.EXTRA_SERVICES,
    ),
    StageTemplate.INTERIORS: (
        BuiltinStage.PROPOSAL,
        BuiltinStage.BRIEFING,
        BuiltinStage.LAYOUT,
        BuiltinStage.MODEL_3D,
        BuiltinStage.DETAILING,
        BuiltinStage.FINAL_DELIVERY,
    ),
    StageTemplate.EMPTY: (),
}

# The project type a new project gets from its template, until staff change it.
TEMPLATE_PROJECT_TYPE: dict[StageTemplate, ProjectType] = {
    StageTemplate.STANDARD: ProjectType.ARCHITECTURE,
    StageTemplate.INTERIORS: ProjectType.INTERIORS,
    StageTemplate.EMPTY: ProjectType.ARCHITECTURE,
}


class DetailType(StrEnum):
    TEXT = "text"
    AREA = "area"  # square metres, a number
    DATE = "date"


class DetailKey(StrEnum):
    CLIENT = "client"
    LOCATION = "location"
    SITE_AREA = "site_area"
    BUILT_AREA = "built_area"
    START_DATE = "start_date"
    EXPECTED_DELIVERY = "expected_delivery"
    RESPONSIBLE = "responsible"


DETAIL_TYPES: dict[DetailKey, DetailType] = {
    DetailKey.CLIENT: DetailType.TEXT,
    DetailKey.LOCATION: DetailType.TEXT,
    DetailKey.SITE_AREA: DetailType.AREA,
    DetailKey.BUILT_AREA: DetailType.AREA,
    DetailKey.START_DATE: DetailType.DATE,
    DetailKey.EXPECTED_DELIVERY: DetailType.DATE,
    DetailKey.RESPONSIBLE: DetailType.TEXT,
}

# Paths of the office's address that can never be a project's slug: the app's own,
# and those Cloud Run's front end answers itself (checked on staging 15 Oct 2026:
# /healthz and /statusz never reach the app; /readyz, /livez, /casa-da-luz do).
RESERVED_SLUGS = ("painel", "api", "static", "assets", "health", "healthz", "statusz")
