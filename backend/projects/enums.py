"""Fixed sets of values for projects (plan A26, A27).

Two kinds of enum live here:

- Values the code acts on (status, access mode, a detail's value type): stored as
  text with a CHECK built from the enum.
- Names of built-in content rows (project types, built-in stages, detail
  types): the rows themselves, with their texts in every language,
  are reference tables in the database (migration 0008), which columns reference
  by foreign key. These enums let code name a specific built-in with autocomplete;
  a test keeps them and the rows in step. Offices' own rows (later) have keys no
  enum lists.
"""

from __future__ import annotations

from enum import StrEnum


class ProjectStatus(StrEnum):
    DRAFT = "draft"  # Rascunho: staff only; the client page answers "not found"
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"  # still viewable; no new uploads or emails (plan section 22)


class CoverType(StrEnum):
    """A cover photo's type, read from its bytes; also its Content-Type."""

    PNG = "image/png"
    JPEG = "image/jpeg"
    WEBP = "image/webp"


class AccessMode(StrEnum):
    PUBLIC = "public"
    PASSWORD = "password"


class ProjectType(StrEnum):
    ARCHITECTURE = "architecture"
    INTERIORS = "interiors"
    RENOVATION = "renovation"
    LANDSCAPING = "landscaping"


class BuiltinStage(StrEnum):
    """The 12 built-in stages (A27), in the order every project lists them."""

    BRIEFING = "briefing"
    SURVEY = "survey"
    SURVEY_ASSESSMENT = "survey_assessment"
    FEASIBILITY_STUDY = "feasibility_study"
    PRELIMINARY_STUDY = "preliminary_study"
    SCHEMATIC_DESIGN = "schematic_design"
    PERMIT_DOCUMENTS = "permit_documents"
    CONSTRUCTION_DOCUMENTS = "construction_documents"
    DETAILING = "detailing"
    COORDINATION = "coordination"
    COMPLEMENTARY_PROJECTS = "complementary_projects"
    SPECIFICATIONS = "specifications"


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


# Paths of the office's address that can never be a project's slug: the app's own,
# and those Cloud Run's front end answers itself (checked on staging 15 Oct 2026:
# /healthz and /statusz never reach the app; /readyz, /livez, /casa-da-luz do).
RESERVED_SLUGS = ("painel", "api", "static", "assets", "health", "healthz", "statusz")
