// Screenshots of the staff app for pull requests (`make screenshots PR=<n>`).
// Not part of `make e2e`: tagged @screenshots and run only on request. Uses the
// same setup as the browser tests (built app, fresh fictional database).
import { execFileSync } from "node:child_process";
import { mkdirSync } from "node:fs";

import { type Page, test } from "@playwright/test";

import { E2E_ENV, OPERATOR, PORT } from "../playwright.config";

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
      animations: "disabled", // a dialog or menu still fading in is shot finished, whatever the test forgot
    });
  }
}

test("@screenshots owner signup", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  mkdirSync(OUT, { recursive: true });
  const output = execFileSync(
    "uv",
    ["run", "python", "-m", "backend.commands.staff", "owner-link", "--tenant", "alinea"],
    { cwd: "..", env: { ...process.env, ...E2E_ENV }, encoding: "utf-8" },
  );
  await page.goto(output.match(/http\S+#token=\S+/)![0].replace(/:\d+\//, `:${PORT}/`));
  await page.getByRole("heading", { name: "Criar a conta de proprietário do Alinea (dev)" }).waitFor();
  await shoot(page, "02b-criar-proprietario");
  await shoot(page, "02b-criar-proprietario", "dark");
});

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
  // An iPad, upright and sideways: "Novo projeto" stays on the search's row.
  for (const tablet of [{ name: "ipad", width: 820, height: 1180 }, { name: "ipad-wide", width: 1180, height: 820 }]) {
    await page.setViewportSize(tablet);
    await page.screenshot({ path: `${OUT}/03-projetos-${tablet.name}.png` });
  }
  await page.setViewportSize(SIZES[0]!);
  // Drive disconnected ("Desconectar"): the projects hidden behind the empty state.
  await page.route("**/api/drive", (route) =>
    route.fulfill({
      json: { kind: "google", writer_status: "none", reader_status: "ok", account_email: "ana@alinea.example",
              folder_url: null, can_manage: true, has_folder: true },
    }),
  );
  await page.reload();
  await page.getByRole("region", { name: "Google Drive desconectado" }).waitFor();
  await shoot(page, "03g-drive-desconectado");
  await page.unroute("**/api/drive");
  await page.reload();
  await page.getByRole("region", { name: "Em andamento" }).waitFor();
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
  await page.getByRole("button", { name: "Opções do projeto Casa Jardim" }).click();
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
  await page.getByRole("heading", { name: "Armazenamento" }).waitFor();
  await shoot(page, "05-configuracoes-drive");

  await page.goto("/painel/configuracoes/equipe");
  await page.getByRole("button", { name: "Convidar pessoa" }).waitFor();
  await shoot(page, "05b-configuracoes-equipe");
  await page.getByRole("button", { name: "Convidar pessoa" }).click();
  await page.getByRole("dialog").waitFor();
  await shoot(page, "05c-convidar-pessoa");
  await page.keyboard.press("Escape");

  // The shared link's page (a new device, not signed in), then the code screen.
  const joinLink = await page.evaluate(async () => {
    const me = await (await fetch("/api/me")).json();
    const made = await fetch("/api/team/join-link", { method: "POST", headers: { "X-CSRF-Token": me.csrf_token } });
    return (await made.json()).link as string;
  });
  const joining = await (await browser.newContext()).newPage();
  await joining.emulateMedia({ reducedMotion: "reduce" });
  await joining.goto(joinLink.replace(/:\d+\//, `:${PORT}/`));
  await joining.getByRole("heading", { name: "Entrar na equipe do Alinea (dev)" }).waitFor();
  await shoot(joining, "05d-entrar-na-equipe");
  await joining.setViewportSize(SIZES[0]!);
  await joining.getByLabel("Nome").fill("Caio Reis");
  await joining.getByLabel("E-mail").fill("caio.reis@exemplo.com.br");
  await joining.getByLabel("Nova senha").fill("senha-das-capturas");
  await joining.getByLabel("Repita a senha").fill("senha-das-capturas");
  await joining.getByRole("button", { name: "Criar conta" }).click();
  await joining.getByRole("heading", { name: "Confirme seu e-mail" }).waitFor();
  await shoot(joining, "05e-confirmar-email");
  await joining.getByRole("button", { name: "Corrigir e-mail" }).click();
  await shoot(joining, "05f-corrigir-email");
  await joining.context().close();
  await page.reload();
  await page.getByText("E-mail não confirmado").waitFor();
  await shoot(page, "05g-equipe-nao-confirmado");

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
  await page.getByRole("heading", { name: "Etapas do projeto" }).waitFor();
  await shoot(page, "06-pagina-do-cliente");
  await shoot(page, "06-pagina-do-cliente", "dark");
  // Drive disconnected: the page is offline (staff are told to reconnect).
  await page.route("**/api/pages/casa-jardim", (route) =>
    route.fulfill({ status: 503, json: { error: "page_unavailable" } }),
  );
  await page.reload();
  await page.getByRole("heading", { name: "Página indisponível" }).waitFor();
  await shoot(page, "06k-pagina-indisponivel");
  await page.unroute("**/api/pages/casa-jardim");
  await page.reload();
  await page.getByRole("heading", { name: "Etapas do projeto" }).waitFor();
  // The file tools: the list view, then a file's preview.
  await page.setViewportSize(SIZES[0]!);
  await page.getByRole("button", { name: "Visualizar em lista" }).first().click();
  await shoot(page, "06d-arquivos-em-lista");
  await page.getByRole("button", { name: "Visualizar miniaturas" }).first().click();
  await page.getByRole("button", { name: "Abrir Plantas.pdf" }).click();
  await page.getByRole("dialog").waitFor();
  await shoot(page, "06e-pre-visualizacao");
  await page.getByRole("button", { name: "Fechar" }).click();
  // A file's versions (A25): "Plantas.pdf" and "Plantas v2.pdf" in the seed.
  await page.getByRole("button", { name: "2 versões" }).click();
  await page.getByRole("dialog", { name: "Plantas.pdf" }).waitFor();
  await shoot(page, "06n-versoes");
  await page.getByRole("dialog").getByRole("button", { name: "Fechar" }).click();
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
  await page.getByRole("button", { name: "Ações para Plantas.pdf" }).click();
  await page.getByRole("menuitem", { name: /Enviar nova versão/ }).waitFor();
  await shoot(page, "06l-menu-do-arquivo"); // "Enviar nova versão" first (A25)
  await page.getByRole("menuitem", { name: "Mover para…" }).click();
  await page.getByRole("menu", { name: /^Mover/ }).waitFor();
  await shoot(page, "06f-mover-arquivo");
  // A file named like one already in the stage: "É uma nova versão?" (A25). Closed
  // unanswered, so nothing is sent.
  await page.keyboard.press("Escape");
  await page
    .locator("#stage-2")
    .getByLabel("escolha no computador")
    .setInputFiles({ name: "Plantas.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4") });
  await page.getByRole("alertdialog", { name: "É uma nova versão?" }).waitFor();
  await shoot(page, "06m-nova-versao");
  await page.keyboard.press("Escape");

  // Details are added from a menu (no select marking its placeholder as chosen).
  await page.goto("/casa-jardim");
  await page.getByRole("navigation", { name: "Ferramentas do escritório" }).getByRole("button", { name: "Editar" }).click();
  await page.getByRole("button", { name: "Editar informações" }).click();
  await page.getByRole("button", { name: "Adicionar informação" }).click();
  await page.getByRole("menu").waitFor();
  await shoot(page, "06o-adicionar-informacao");
  await page.keyboard.press("Escape");

  // A note to the client is news for "Atualizações" (A28): seen as a visitor.
  await page.goto("/casa-jardim");
  await page.getByRole("navigation", { name: "Ferramentas do escritório" }).getByRole("button", { name: "Editar" }).click();
  await page.locator("#stage-2").getByRole("button", { name: "Recado para o cliente" }).click();
  // "Recado para o cliente" opens the stage's "Editar etapa": its name, note, uploads and remove.
  await page.getByLabel("Recado da etapa").fill("As plantas da sala estão prontas para a sua revisão.");
  await page.locator("#stage-2").scrollIntoViewIfNeeded();
  await shoot(page, "06i-etapa-editando");
  await page.locator("#stage-2").getByRole("button", { name: "Salvar" }).click();
  await page.locator("#stage-2").getByText("As plantas da sala estão prontas para a sua revisão.").waitFor();
  // "Reordenar etapas": the whole row drags (a hold on a phone).
  await page.goto("/casa-jardim");
  await page.getByRole("navigation", { name: "Ferramentas do escritório" }).getByRole("button", { name: "Editar" }).click();
  await page.getByRole("button", { name: "Reordenar etapas" }).click();
  await page.getByRole("dialog", { name: "Reordenar etapas" }).waitFor();
  await page.locator(".stage-order__row").nth(1).hover();
  await shoot(page, "06q-reordenar-etapas");
  await page.keyboard.press("Escape");
  // "Adicionar etapa", naming one of the office's own: Adicionar beside Cancelar.
  await page.goto("/casa-jardim");
  await page.getByRole("navigation", { name: "Ferramentas do escritório" }).getByRole("button", { name: "Editar" }).click();
  await page.getByRole("button", { name: "+ Adicionar etapa" }).click();
  await page.locator(".add-stage select").selectOption({ label: "Etapa personalizada…" });
  await page.getByLabel("Nome da etapa").fill("Visita técnica");
  await page.locator(".add-stage").scrollIntoViewIfNeeded();
  await shoot(page, "06r-adicionar-etapa");
  await page.locator(".add-stage").getByRole("button", { name: "Cancelar" }).click();
  // A stage's sections: a new one, empty, with its own drop area (staff only).
  const closed = page.locator("#stage-2").getByRole("button", { name: /^Abrir etapa/ });
  if (await closed.count()) await closed.click();
  await page.locator("#stage-2").getByRole("button", { name: "+ Nova seção" }).click();
  await page.locator("#stage-2").getByLabel("Nome da seção").fill("Plantas executivas");
  await page.keyboard.press("Enter");
  await page.locator("#stage-2").getByRole("button", { name: "+ Nova seção" }).waitFor(); // saved
  await page.locator("#stage-2").getByRole("heading", { name: "Plantas executivas" }).scrollIntoViewIfNeeded();
  await shoot(page, "06s-nova-secao");
  // Reopening a stage says the client will be emailed (A32), as completing does.
  await page.goto("/casa-jardim");
  await page.getByRole("navigation", { name: "Ferramentas do escritório" }).getByRole("button", { name: "Editar" }).click();
  await page.getByRole("button", { name: "Abrir etapa Levantamento" }).click(); // completed in the seed
  await page.getByRole("button", { name: "Reabrir etapa" }).click();
  const reopen = page.getByRole("alertdialog", { name: "Reabrir “Levantamento”?" });
  await reopen.waitFor();
  await shoot(page, "06p-reabrir-etapa");
  await reopen.getByRole("button", { name: "Reabrir etapa" }).click();
  await reopen.waitFor({ state: "detached" });
  const visitor = await browser.newPage();
  await visitor.emulateMedia({ reducedMotion: "reduce" });
  await visitor.goto("/casa-jardim");
  // The note, and the stage reopened above ("Etapa reaberta").
  await visitor.getByLabel(/Últimas atualizações, 2 não lidas/).click();
  await visitor.getByRole("region", { name: "Últimas atualizações" }).waitFor();
  await shoot(visitor, "06c-atualizacoes");
  await visitor.keyboard.press("Escape");

  // Sharing files by link (A37): from a stage, its files ticked; then the link;
  // then the supplier's page it opens.
  await visitor.getByRole("button", { name: /^Compartilhar arquivos de / }).first().click();
  const share = visitor.getByRole("dialog", { name: "Compartilhar arquivos" });
  await share.waitFor();
  await share.getByLabel("Para quem? (Opcional)").fill("Marcenaria Silva");
  await shoot(visitor, "09-compartilhar-arquivos");
  await share.getByRole("button", { name: "Gerar link" }).click();
  const ready = visitor.getByRole("dialog", { name: "Link pronto" });
  await ready.waitFor();
  await shoot(visitor, "09b-link-pronto");
  const url = await ready.getByLabel("Link para compartilhar").inputValue();
  await visitor.goto(new URL(url).pathname);
  await visitor.getByRole("heading", { name: "Arquivos compartilhados" }).waitFor();
  await shoot(visitor, "09c-pagina-do-fornecedor");
  await shoot(visitor, "09c-pagina-do-fornecedor", "dark");
  // Back on the project, this device's link is listed.
  await visitor.goto("/casa-jardim");
  await visitor.getByRole("button", { name: "Compartilhar arquivos", exact: true }).click();
  await visitor.getByRole("tab", { name: /^Links criados/ }).click();
  await visitor.getByRole("region", { name: "Links criados neste dispositivo" }).getByText("Marcenaria Silva").waitFor();
  await shoot(visitor, "09d-links-do-dispositivo");
  await visitor.keyboard.press("Escape");
  // A link with a password: the supplier types it first.
  await visitor.getByRole("button", { name: /^Compartilhar arquivos de / }).first().click();
  const locked = visitor.getByRole("dialog", { name: "Compartilhar arquivos" });
  await locked.getByLabel("Senha (opcional)").fill("marcenaria");
  await locked.getByRole("button", { name: "Gerar link" }).click();
  const lockedUrl = await visitor.getByRole("dialog", { name: "Link pronto" }).getByLabel("Link para compartilhar").inputValue();
  await visitor.goto(new URL(lockedUrl).pathname);
  await visitor.getByRole("heading", { name: "Arquivos protegidos" }).waitFor();
  await shoot(visitor, "09f-link-com-senha");
  // Staff see every link of the project, the dialog above the staff bar.
  await page.goto("/casa-jardim");
  await page.getByRole("button", { name: "Compartilhar arquivos", exact: true }).click();
  await page.getByRole("tab", { name: /^Links criados/ }).click();
  await page.getByRole("region", { name: "Links deste projeto" }).getByText("Marcenaria Silva").waitFor();
  await shoot(page, "09e-links-do-projeto");
  await page.keyboard.press("Escape");

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

// The preview page (plan section 18, "Visual variants"): the panel, then the page
// alone in a few combinations, by the same addresses a person would share.
test("@screenshots preview page", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  mkdirSync(OUT, { recursive: true });
  await page.goto("/painel/previa?width=phone&meeting=long&longNames=1");
  await page.frameLocator("iframe").getByRole("heading", { level: 1 }).waitFor();
  for (const size of SIZES) {
    await page.setViewportSize(size);
    await page.screenshot({ path: `${OUT}/08-previa-painel-${size.name}.png` });
  }
  const combinations = {
    "08b-previa-sem-capa-nomes-longos": "cover=0&longNames=1&files=6&meeting=long",
    "08c-previa-minima": "cover=0&description=none&meeting=none&stages=1&files=0",
    "08d-previa-equipe-sem-emails": "view=staff&emails=0&description=short",
  };
  for (const [name, query] of Object.entries(combinations)) {
    await page.goto(`/painel/previa?frame&${query}`);
    await page.getByRole("heading", { level: 1 }).waitFor();
    await shoot(page, name);
  }
});

test("@screenshots operator dashboard", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" }); // no half-faded dialogs
  mkdirSync(OUT, { recursive: true });
  const unio = `http://localhost:${PORT}`;
  await page.goto(`${unio}/admin`);
  await page.getByRole("button", { name: "Entrar com Google" }).waitFor();
  await shoot(page, "10-operacao-entrar");
  await page.getByLabel(/E-mail autorizado/).fill(OPERATOR);
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await page.getByRole("table").waitFor();
  await shoot(page, "10b-operacao-escritorios");
  await page.getByRole("button", { name: "Criar escritório", exact: true }).click();
  await page.getByLabel("Nome do escritório").fill("Ateliê Horizonte");
  await page.getByLabel("Endereço do escritório no Unio", { exact: true }).fill("horizonte");
  await shoot(page, "10d-operacao-criar");
  await page.keyboard.press("Escape");
  await page.getByRole("link", { name: "Alinea (dev)" }).click();
  await page.getByRole("heading", { name: "Equipe" }).waitFor();
  await page.getByRole("button", { name: "Carregar estatísticas de arquivos" }).click();
  await page.getByText("PDF", { exact: true }).waitFor();
  await shoot(page, "10c-operacao-escritorio");
  await page.getByRole("button", { name: "Suspender", exact: true }).click();
  await shoot(page, "10e-operacao-suspender");
});
