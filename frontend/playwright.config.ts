import { defineConfig, devices } from "@playwright/test";

// The built staff app, served by the real Python backend on a fresh local
// database (backend.commands.e2e), signed in as the app's restricted login.
// Run with `make e2e`, which builds first.
export const PORT = 8010;
const OWNER = "postgresql+psycopg://localhost:5432/arqproj_e2e";
const APP = "postgresql+psycopg://arqproj_app@localhost:5432/arqproj_e2e";
export const E2E_ENV = { MIGRATION_DATABASE_URL: OWNER, DATABASE_URL: APP };

export default defineConfig({
  testDir: "e2e",
  fullyParallel: false,
  reporter: [["list"]],
  use: { baseURL: `http://alinea.localhost:${PORT}`, trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `uv run python -m backend.commands.e2e && uv run uvicorn backend.app:create_app --factory --port ${PORT}`,
    cwd: "..",
    env: { ...E2E_ENV, FRONTEND_DIST: `${import.meta.dirname}/dist` },
    url: `http://127.0.0.1:${PORT}/health`,
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
