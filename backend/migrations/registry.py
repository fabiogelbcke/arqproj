"""Imports every model module so Base.metadata lists all tables.

Alembic and the schema tests read Base.metadata; a model module missing here
would silently drop out of migration checks.
"""

from backend.db.base import Base
from backend.identity import models as identity_models  # noqa: F401
from backend.tenancy import models as tenancy_models  # noqa: F401

metadata = Base.metadata
