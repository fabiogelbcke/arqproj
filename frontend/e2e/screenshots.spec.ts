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

test("@screenshots staff app", async ({ page, browser }) => {
  await page.emulateMedia({ reducedMotion: "reduce" }); // no half-faded dialogs
  mkdirSync(OUT, { recursive: true });
  await page.goto("/painel/entrar");
  await page.getByRole("heading", { name: "Entrar" }).waitFor();
  await shoot(page, "01-entrar");

  await page.getByRole("link", { name: "Esqueceu a senha?" }).click();
  await page.getByRole("heading", { name: "Esqueceu a senha?" }).waitFor();
  await shoot(page, "01b-esqueci-a-senha");
  await page.getByLabel("E-mail").fill("ana@alinea.example");
  await page.getByRole("button", { name: "Enviar link" }).click();
  await page.getByRole("heading", { name: "Confira seu e-mail" }).waitFor();
  await shoot(page, "01c-link-enviado");

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
  // Cropped first, its empty margins trimmed already.
  await page.getByText("Assim ele aparece no topo das páginas").waitFor();
  await shoot(page, "04b-recortar-logo");
  await page.getByRole("button", { name: "Usar recorte" }).click();
  await page.getByText("Logo atualizado.").waitFor();
  await page.goto("/painel");
  await page.getByRole("heading", { name: "Projetos" }).waitFor();
  await page.locator("header img").waitFor();
  await page.getByRole("region", { name: "Em andamento" }).waitFor(); // the projects, loaded
  await shoot(page, "03-projetos");
  await shoot(page, "03-projetos", "dark");
  // Phones: the ☰ menu, open (a phone-only screen).
  await page.evaluate(() => (document.documentElement.dataset.theme = "light"));
  await page.setViewportSize(SIZES[1]!);
  await page.getByRole("button", { name: "Menu" }).click();
  await page.getByRole("dialog", { name: "Menu" }).waitFor();
  await page.screenshot({ path: `${OUT}/03e-menu-phone.png` });
  await page.keyboard.press("Escape");
  await page.setViewportSize(SIZES[0]!);
  await page.getByRole("button", { name: "Novo projeto" }).click();
  await page.getByLabel("Nome do projeto").fill("Casa do Lago");
  await page.getByLabel("Cliente").fill("Família Souza");
  await shoot(page, "03b-novo-projeto");
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Editar o projeto Casa Jardim" }).click();
  await page.getByRole("menu").waitFor();
  await shoot(page, "03f-menu-do-projeto");
  await page.getByRole("menuitem", { name: "Configurações do projeto" }).click();
  await page.getByRole("dialog", { name: "Projeto" }).waitFor();
  await shoot(page, "03c-projeto");
  const newEmail = page.getByLabel("Novo e-mail");
  await newEmail.fill("lucia.oliveira@exemplo.com.br");
  await newEmail.press("Enter");
  await newEmail.fill("pedro.oliveira@exemplo.com.br");
  await newEmail.press("Enter");
  await newEmail.scrollIntoViewIfNeeded();
  await shoot(page, "03d-projeto-emails");
  await page.keyboard.press("Escape");

  await page.goto("/painel/configuracoes/escritorio");
  await page.getByLabel(/Nome do escritório/).waitFor();
  await shoot(page, "04-configuracoes-escritorio");

  await page.goto("/painel/configuracoes/drive");
  await page.getByRole("heading", { name: "Google Drive" }).waitFor();
  await shoot(page, "05-configuracoes-drive");

  await page.goto("/painel/configuracoes/equipe");
  await page.getByRole("button", { name: "Convidar pessoa" }).waitFor();
  await shoot(page, "05b-configuracoes-equipe");
  await page.getByRole("button", { name: "Convidar pessoa" }).click();
  await page.getByRole("dialog").waitFor();
  await shoot(page, "05c-convidar-pessoa");
  await page.keyboard.press("Escape");

  // The client's page (no sign-in needed; the staff session doesn't change it).
  await page.setViewportSize(SIZES[0]!);
  await page.goto("/casa-jardim");
  // A new account's first project page: the tour, in edit mode. Then closed (seen)
  // and back to the client's view.
  const tour = page.locator(".driver-popover");
  await tour.waitFor();
  await page.waitForTimeout(400); // its fade-in
  await shoot(page, "06i-tour");
  await tour.getByRole("button", { name: /Próximo/ }).click();
  await page.waitForTimeout(400);
  await shoot(page, "06j-tour-lapis");
  const seen = page.waitForResponse((r) => r.url().endsWith("/api/me/tour-seen"));
  await page.keyboard.press("Escape");
  await seen;
  await page.setViewportSize(SIZES[0]!);
  await page.getByRole("navigation", { name: "Ferramentas do escritório" }).getByRole("button", { name: "Ver como cliente" }).click();
  await page.getByRole("heading", { name: "Etapas e próximos passos" }).waitFor();
  await shoot(page, "06-pagina-do-cliente");
  await shoot(page, "06-pagina-do-cliente", "dark");
  // The file tools: the list view, then a file's preview.
  await page.setViewportSize(SIZES[0]!);
  await page.getByRole("button", { name: "Visualizar em lista" }).first().click();
  await shoot(page, "06d-arquivos-em-lista");
  await page.getByRole("button", { name: "Visualizar miniaturas" }).first().click();
  await page.getByRole("button", { name: /^Abrir Plantas v2/ }).click();
  await page.getByRole("dialog").waitFor();
  await shoot(page, "06e-pre-visualizacao");
  await page.getByRole("button", { name: "Fechar" }).click();
  await page.setViewportSize(SIZES[0]!);
  await page.getByRole("navigation", { name: "Ferramentas do escritório" }).getByRole("button", { name: "Editar" }).click();
  await page.getByRole("button", { name: "Editar reunião" }).click();
  await page.locator(".project-status__meeting form").waitFor(); // the editor, loaded
  await shoot(page, "06b-pagina-editando");
  // The cover in edit mode: its place, to add one, or "Trocar capa" on it.
  await page.locator(".project-status__meeting form").getByRole("button", { name: "Cancelar" }).click();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.locator(".cover-empty, .cover-actions").first().waitFor();
  await shoot(page, "06h-capa-editando");
  // A file's menu (A34), moving it to another stage.
  await page.goto("/casa-jardim");
  await page.getByRole("navigation", { name: "Ferramentas do escritório" }).getByRole("button", { name: "Editar" }).click();
  await page.getByRole("button", { name: /^Ações para Plantas v2/ }).click();
  await page.getByRole("menuitem", { name: "Mover para outra etapa" }).click();
  await page.getByRole("menu", { name: /^Mover/ }).waitFor();
  await shoot(page, "06f-mover-arquivo");

  // A note to the client is news for "Atualizações" (A28): seen as a visitor.
  await page.goto("/casa-jardim");
  await page.getByRole("navigation", { name: "Ferramentas do escritório" }).getByRole("button", { name: "Editar" }).click();
  await page.locator("#stage-2").getByRole("button", { name: "Recado para o cliente" }).click();
  await page.getByLabel("Recado da etapa").fill("As plantas da sala estão prontas para a sua revisão.");
  await page.getByRole("button", { name: "Salvar" }).click();
  await page.getByText("As plantas da sala estão prontas para a sua revisão.").waitFor();
  const visitor = await browser.newPage();
  await visitor.emulateMedia({ reducedMotion: "reduce" });
  await visitor.goto("/casa-jardim");
  await visitor.getByLabel(/Últimas atualizações, 1 não lida/).click();
  await visitor.getByRole("region", { name: "Últimas atualizações" }).waitFor();
  await shoot(visitor, "06c-atualizacoes");

  // The example project (plan section 16): its explore tour, then the page.
  await visitor.goto("/tour-projeto");
  const explore = visitor.locator(".driver-popover");
  await explore.waitFor();
  await visitor.waitForTimeout(400); // its fade-in
  await shoot(visitor, "07-exemplo-tour");
  await explore.getByRole("button", { name: "Pular" }).click();
  await shoot(visitor, "07b-projeto-de-exemplo");
  await visitor.close();
});
