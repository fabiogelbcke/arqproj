// Screenshots of the staff app for pull requests (`make screenshots PR=<n>`).
// Not part of `make e2e`: tagged @screenshots and run only on request. Uses the
// same setup as the browser tests (built app, fresh fictional database).
import { execFileSync } from "node:child_process";
import { mkdirSync } from "node:fs";

import { type Page, test } from "@playwright/test";

import { E2E_ENV, PORT } from "../playwright.config";

const OUT = process.env.SCREENSHOTS_DIR ?? "screenshots";
const SIZES = [
  { name: "desktop", width: 1280, height: 860 },
  { name: "phone", width: 390, height: 844 },
];

function invite(email: string): string {
  const output = execFileSync(
    "uv",
    ["run", "python", "-m", "backend.commands.staff", "add", "--tenant", "alinea", "--email", email,
     "--name", "Ana", "--role", "owner"],
    { cwd: "..", env: { ...process.env, ...E2E_ENV }, encoding: "utf-8" },
  );
  return output.match(/http\S+#token=\S+/)![0].replace(/:\d+\//, `:${PORT}/`);
}

async function shoot(page: Page, name: string, theme: "light" | "dark" = "light") {
  await page.evaluate((t) => (document.documentElement.dataset.theme = t), theme);
  for (const size of SIZES) {
    await page.setViewportSize(size);
    await page.screenshot({ path: `${OUT}/${name}-${size.name}${theme === "dark" ? "-dark" : ""}.png`, fullPage: true });
  }
}

test("@screenshots staff app", async ({ page }) => {
  mkdirSync(OUT, { recursive: true });
  await page.goto("/painel/entrar");
  await page.getByRole("heading", { name: "Entrar" }).waitFor();
  await shoot(page, "01-entrar");

  await page.goto(invite("screens@alinea.example"));
  await page.getByRole("heading", { name: "Escolha sua senha" }).waitFor();
  await shoot(page, "02-definir-senha");
  await page.setViewportSize(SIZES[0]!);
  await page.getByLabel("Nova senha").fill("senha-das-capturas");
  await page.getByLabel("Repita a senha").fill("senha-das-capturas");
  await page.getByRole("button", { name: "Salvar senha e entrar" }).click();

  await page.getByRole("heading", { name: "Projetos" }).waitFor();
  await shoot(page, "03-projetos");
  await shoot(page, "03-projetos", "dark");

  await page.goto("/painel/configuracoes/escritorio");
  await page.getByLabel(/Nome do escritório/).waitFor();
  await shoot(page, "04-configuracoes-escritorio");

  await page.goto("/painel/configuracoes/drive");
  await page.getByRole("heading", { name: "Google Drive" }).waitFor();
  await shoot(page, "05-configuracoes-drive");
});
