"""Write the API description (OpenAPI) that the staff app's types are generated from,
and beside it `limits.json`, the fields' length limits (backend/web/limits.py).

    uv run python -m backend.commands.openapi frontend/src/api/openapi.json

`make api-types` runs this, then generates `frontend/src/api/schema.d.ts` from it.
A test fails if either committed file no longer matches the API.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from backend.app import create_app
from backend.settings import Settings
from backend.web.limits import FIELD_LIMITS


def schema() -> str:
    # Settings only shape the docs URLs, not the schema; no database is touched.
    app = create_app(Settings(environment="test"))
    return json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n"


def limits() -> str:
    return json.dumps(FIELD_LIMITS, indent=2) + "\n"


def main() -> int:
    target = Path(sys.argv[1])
    target.write_text(schema(), "utf-8")
    (target.parent / "limits.json").write_text(limits(), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
