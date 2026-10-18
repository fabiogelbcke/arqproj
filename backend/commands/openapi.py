"""Write the API description (OpenAPI) that the staff app's types are generated from.

    uv run python -m backend.commands.openapi frontend/src/api/openapi.json

`make api-types` runs this, then generates `frontend/src/api/schema.d.ts` from it.
A test fails if the committed file no longer matches the API.
"""

from __future__ import annotations

import json
import sys

from backend.app import create_app
from backend.settings import Settings


def schema() -> str:
    # Settings only shape the docs URLs, not the schema; no database is touched.
    app = create_app(Settings(environment="test"))
    return json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    with open(sys.argv[1], "w", encoding="utf-8") as out:
        out.write(schema())
    return 0


if __name__ == "__main__":
    sys.exit(main())
