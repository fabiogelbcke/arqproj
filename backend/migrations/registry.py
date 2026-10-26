"""Imports every model module so Base.metadata lists all tables.

Alembic and the schema tests read Base.metadata; a model module missing here
would silently drop out of migration checks.
"""

from backend.db.base import Base
from backend.identity import models as identity_models  # noqa: F401
from backend.notifications import models as notification_models  # noqa: F401
from backend.office import models as office_models  # noqa: F401
from backend.projects import models as project_models  # noqa: F401
from backend.shares import models as share_models  # noqa: F401
from backend.storage import models as storage_models  # noqa: F401
from backend.tenancy import models as tenancy_models  # noqa: F401

metadata = Base.metadata

# Advisory lock key held while migrations run (env.py).
MIGRATION_LOCK = 7_202_610
