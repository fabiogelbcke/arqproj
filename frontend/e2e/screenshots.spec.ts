// Screenshots of the staff app for pull requests (`make screenshots PR=<n>`).
// Not part of `make e2e`: tagged @screenshots and run only on request. Uses the
// same setup as the browser tests (built app, fresh fictional database).
import { execFileSync } from "node:child_process";
import { mkdirSync } from "node:fs";

import { type Page, test } from "@playwright/test";

import { E2E_ENV, PORT } from "../playwright.config";

const OUT = process.env.SCREENSHOTS_DIR ?? "screenshots";
// A fictional mark (a slanted square), like the prototype's logo.
const LOGO = Buffer.from(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 27 29"><path d="M0 9 L18 0 L27 6 L27 20 L9 29 L4 21 Z" fill="#242629"/></svg>',
);
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

/** The whole page; a dialog is shot as the screen shows it (it covers the screen, not the page). */
async function shoot(page: Page, name: string, theme: "light" | "dark" = "light") {
  await page.evaluate((t) => (document.documentElement.dataset.theme = t), theme);
  const dialog = (await page.getByRole("dialog").count()) > 0;
  for (const size of SIZES) {
    await page.setViewportSize(size);
    await page.screenshot({
      path: `${OUT}/${name}-${size.name}${theme === "dark" ? "-dark" : ""}.png`,
      fullPage: !dialog,
    });
  }
}

test("@screenshots staff app", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" }); // no half-faded dialogs
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

  // A fictional logo, so the header shows one.
  await page.goto("/painel/configuracoes/escritorio");
  await page.getByRole("button", { name: "Escolher imagem" }).waitFor();
  await page.locator('input[type="file"]').setInputFiles({ name: "logo.svg", mimeType: "image/svg+xml", buffer: LOGO });
  await page.getByText("Logo atualizado.").waitFor();
  await page.goto("/painel");
  await page.getByRole("heading", { name: "Projetos" }).waitFor();
  await page.locator("header img").waitFor();
  await shoot(page, "03-projetos");
  await shoot(page, "03-projetos", "dark");
  await page.getByRole("button", { name: "Novo projeto" }).click();
  await page.getByLabel("Nome do projeto").fill("Casa do Lago");
  await page.getByLabel("Cliente").fill("Família Souza");
  await shoot(page, "03b-novo-projeto");
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Editar o projeto Casa Jardim" }).click();
  await page.getByRole("dialog", { name: "Projeto" }).waitFor();
  await shoot(page, "03c-projeto");
  await page.keyboard.press("Escape");

  await page.goto("/painel/configuracoes/escritorio");
  await page.getByLabel(/Nome do escritório/).waitFor();
  await shoot(page, "04-configuracoes-escritorio");

  await page.goto("/painel/configuracoes/drive");
  await page.getByRole("heading", { name: "Google Drive" }).waitFor();
  await shoot(page, "05-configuracoes-drive");

  // The client's page (no sign-in needed; the staff session doesn't change it).
  await page.setViewportSize(SIZES[0]!);
  await page.goto("/casa-jardim");
  await page.getByRole("heading", { name: "Etapas e próximos passos" }).waitFor();
  await shoot(page, "06-pagina-do-cliente");
  await shoot(page, "06-pagina-do-cliente", "dark");
  await page.setViewportSize(SIZES[0]!);
  await page.getByRole("navigation", { name: "Ferramentas do escritório" }).getByRole("button", { name: "Editar" }).click();
  await page.getByRole("button", { name: "Editar reunião" }).click();
  await shoot(page, "06b-pagina-editando");
});
