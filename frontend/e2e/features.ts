// Features are switched on per office from the operator dashboard (A40); the
// browser tests switch one on for Alinea straight in the test database.
import { execFileSync } from "node:child_process";

import { E2E_ENV } from "../playwright.config";

export function switchOn(feature: string) {
  execFileSync(
    "uv",
    ["run", "python", "-c", [
      "import os, sqlalchemy as sa",
      "engine = sa.create_engine(os.environ['MIGRATION_DATABASE_URL'])",
      `with engine.begin() as db: db.execute(sa.text("UPDATE tenants SET features = array_append(features, '${feature}') WHERE slug = 'alinea' AND NOT '${feature}' = ANY(features)"))`,
    ].join("\n")],
    { cwd: "..", env: { ...process.env, ...E2E_ENV } },
  );
}
