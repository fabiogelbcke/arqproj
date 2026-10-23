import { execFileSync } from "node:child_process";

import { expect, test, type Page } from "@playwright/test";

// The staff app runs under a strict Content Security Policy (plan section 4).
// Anything the build needs that the policy blocks shows up as a console error.
test.beforeEach(({ page, browserName }) => {
  page.on("console", (message) => {
    // WebKit reports its own styling of a native <select> as a blocked inline style
    // ("Refused to apply a stylesheet", style-src-attr); nothing of ours is blocked.
    // Chromium runs every test and still catches anything real.
    if (browserName === "webkit" && /^Refused to apply a stylesheet/.test(message.text())) return;
    if (/Content Security Policy/i.test(message.text())) throw new Error(message.text());
  });
});

import { E2E_ENV, PORT } from "../playwright.config";

/** An account made the real way, with the staff command; returns its invite link. */
/** The project page's tour is for new accounts; tests about other things mark it
 *  seen, as finishing it would (the tour has its own test). */
async function skipTour(page: Page) {
  await page.getByRole("heading", { name: "Projetos" }).waitFor();
  const me = await (await page.request.get("/api/me")).json();
  await page.request.post("/api/me/tour-seen", { headers: { "X-CSRF-Token": me.csrf_token } });
}

function invite(email: string, role: "owner" | "member" = "member"): string {
  const output = execFileSync(
    "uv",
    ["run", "python", "-m", "backend.commands.staff", "add", "--tenant", "alinea", "--email", email, "--name", "Teste", "--role", role],
    { cwd: "..", env: { ...process.env, ...E2E_ENV }, encoding: "utf-8" },
  );
  const link = output.match(/http\S+#token=\S+/)?.[0];
  if (!link) throw new Error(`no link in: ${output}`);
  return link.replace(/:\d+\//, `:${PORT}/`);
}

test("invite → choose password → projects → deep link → sign out → sign in", async ({ page }) => {
  const link = invite("teste@alinea.example");

  await page.goto(link);
  await expect(page.getByRole("heading", { name: "Escolha sua senha" })).toBeVisible();
  await expect(page).not.toHaveURL(/token=/); // taken out of the address bar
  await page.getByLabel("Nova senha").fill("senha-escolhida");
  await page.getByLabel("Repita a senha").fill("senha-escolhida");
  await page.getByRole("button", { name: "Salvar senha e entrar" }).click();
  await expect(page.getByRole("heading", { name: "Projetos" })).toBeVisible();

  // A deep link survives a reload: the server returns the shell, the app routes.
  await page.goto("/painel/a/deep/link");
  await expect(page.getByRole("heading", { name: "Página não encontrada" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Página não encontrada" })).toBeVisible();

  // Sair is in the account menu, under the round initial (painel redesign).
  await page.getByRole("button", { name: "Sua conta" }).click();
  await page.getByRole("menuitem", { name: "Sair" }).click();
  await expect(page.getByRole("heading", { name: "Entrar" })).toBeVisible();
  await page.goto("/painel");
  await expect(page).toHaveURL(/\/painel\/entrar/); // signed out for real

  await page.getByLabel("E-mail").fill("teste@alinea.example");
  await page.getByLabel("Senha", { exact: true }).fill("senha errada");
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page.getByRole("alert")).toContainText("E-mail ou senha incorretos.");
  await expect(page.getByRole("alert")).toContainText("Código de suporte:");

  await page.getByLabel("Senha", { exact: true }).fill("senha-escolhida");
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page.getByRole("heading", { name: "Projetos" })).toBeVisible();

  // The invite link was spent.
  await page.goto(link);
  await expect(page.getByRole("heading", { name: "Este link não funciona mais" })).toBeVisible();
});

test("a chosen logo is cropped in the browser, its empty margins trimmed, and goes up as a PNG", async ({ page }) => {
  const link = invite("marca@alinea.example", "owner"); // only owners change the logo
  await page.goto(link);
  await page.getByLabel("Nova senha").fill("senha-escolhida");
  await page.getByLabel("Repita a senha").fill("senha-escolhida");
  await page.getByRole("button", { name: "Salvar senha e entrar" }).click();
  await page.getByRole("heading", { name: "Projetos" }).waitFor();

  // A 3:1 logo in the middle of a square of empty space, as logos often come.
  const svg = Buffer.from(
    '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400" viewBox="0 0 400 400">' +
      '<rect x="50" y="150" width="300" height="100" fill="#43543b"/>' +
      '<text x="70" y="215" font-size="48" fill="#ffffff" font-family="sans-serif">ALINEA</text></svg>',
  );
  await page.goto("/painel/configuracoes/escritorio");
  await page.getByRole("button", { name: "Escolher imagem" }).waitFor();
  await page.locator('input[type="file"]').setInputFiles({ name: "logo.svg", mimeType: "image/svg+xml", buffer: svg });
  const crop = page.getByRole("dialog", { name: "Ajustar o logo" });
  await expect(crop.getByText("Assim ele aparece no topo das páginas")).toBeVisible();
  await crop.getByRole("button", { name: "Usar recorte" }).click();
  await page.getByText("Logo atualizado.").waitFor();

  const logo = await page.request.get("/api/office/logo");
  expect(logo.headers()["content-type"]).toBe("image/png"); // email programs show it too
  const bytes = await logo.body();
  // Width and height from the PNG's header: about the drawing's 3:1, not the square.
  const [width, height] = [bytes.readUInt32BE(16), bytes.readUInt32BE(20)];
  expect(width).toBe(1200);
  expect(width / height).toBeGreaterThan(2.6);
  expect(width / height).toBeLessThan(3.2);
});

test("a session belongs to its office's address", async ({ page }) => {
  const link = invite("outro@alinea.example");
  await page.goto(link);
  await page.getByLabel("Nova senha").fill("senha-escolhida");
  await page.getByLabel("Repita a senha").fill("senha-escolhida");
  await page.getByRole("button", { name: "Salvar senha e entrar" }).click();
  await expect(page.getByRole("heading", { name: "Projetos" })).toBeVisible();

  await page.goto(`http://norte.localhost:${PORT}/painel`);
  await expect(page.getByRole("heading", { name: "Entrar" })).toBeVisible();
});

test("create a project → it is listed as a draft; a used address names its project", async ({ page }) => {
  const link = invite("projetos@alinea.example");
  await page.goto(link);
  await page.getByLabel("Nova senha").fill("senha-escolhida");
  await page.getByLabel("Repita a senha").fill("senha-escolhida");
  await page.getByRole("button", { name: "Salvar senha e entrar" }).click();
  await expect(page.getByRole("heading", { name: "Em andamento" })).toBeVisible();

  // An address another project already has.
  await page.getByRole("button", { name: "Novo projeto" }).click();
  const dialog = page.getByRole("dialog", { name: "Novo projeto" });
  await dialog.getByLabel("Nome do projeto").fill("Casa Jardim");
  await dialog.getByLabel("Cliente").fill("Família Teste");
  await expect(dialog.getByLabel("Endereço da página")).toHaveValue("casa-jardim"); // from the name
  await dialog.getByRole("button", { name: "Criar projeto" }).click();
  await expect(dialog.getByRole("alert")).toContainText("Este endereço já é do projeto “Casa Jardim”");

  // Changing the address alone is not enough: the name is taken too.
  await dialog.getByLabel("Endereço da página").fill("casa-jardim-teste");
  await dialog.getByRole("button", { name: "Criar projeto" }).click();
  await expect(dialog.getByRole("alert")).toContainText("Já existe o projeto “Casa Jardim”");
  await dialog.getByLabel("Nome do projeto").fill("Casa Jardim Teste");
  await dialog.getByText("Projeto de Interiores", { exact: true }).click();
  await expect(dialog.getByRole("radio", { name: "Projeto de Interiores" })).toBeChecked();
  await expect(dialog.getByRole("checkbox", { name: "Especificações" })).toBeChecked(); // usual for interiors
  await dialog.getByText("Especificações", { exact: true }).click(); // untick one
  await dialog.getByRole("button", { name: "Criar projeto" }).click();
  await expect(dialog).toBeHidden();

  // Published at once (A35): with the live projects, no drafts group.
  const live = page.getByRole("region", { name: "Em andamento" });
  const card = live.getByTestId("project-card").filter({ hasText: "Família Teste" });
  await expect(page.getByRole("region", { name: "Rascunhos" })).toHaveCount(0);
  await expect(card).toContainText("1 / 6");
  await expect(card).toContainText("Projeto de Interiores");

  // Search ignores accents and case.
  await page.getByRole("searchbox", { name: "Buscar projetos" }).fill("familia teste");
  await expect(page.getByTestId("project-card")).toHaveCount(1);
  await page.getByRole("searchbox", { name: "Buscar projetos" }).fill("nada parecido");
  await expect(page.getByText(/Nenhum projeto encontrado para/)).toBeVisible();
});

// A real 1×1 PNG, so the browser can preview it.
const PNG_1PX = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
  "base64",
);

test("the card's menu: the photo, then the settings, then archive (confirmed) and undo", async ({ page }) => {
  const link = invite("ajustes@alinea.example");
  await page.goto(link);
  await page.getByLabel("Nova senha").fill("senha-escolhida");
  await page.getByLabel("Repita a senha").fill("senha-escolhida");
  await page.getByRole("button", { name: "Salvar senha e entrar" }).click();

  // A completed project (its group is open too): the card's "⋯" and its menu.
  const menu = (name: string) => page.getByRole("button", { name: `Opções do projeto ${name}` }).click();
  await menu("Refúgio da Mantiqueira");
  // The photo straight from the menu, cropped to the cover's shape first.
  const [chooser] = await Promise.all([
    page.waitForEvent("filechooser"),
    page.getByRole("menuitem", { name: "Adicionar foto" }).click(),
  ]);
  await chooser.setFiles({ name: "obra.png", mimeType: "image/png", buffer: PNG_1PX });
  await page.getByRole("dialog", { name: "Ajustar a capa" }).getByRole("button", { name: "Usar recorte" }).click();
  await expect(page.getByText("Foto atualizada.")).toBeVisible();

  await menu("Refúgio da Mantiqueira");
  await expect(page.getByRole("menuitem", { name: "Remover foto" })).toBeVisible(); // it has one now
  await page.getByRole("menuitem", { name: "Configurações do projeto" }).click();
  const settings = page.getByRole("dialog", { name: "Projeto" });
  await settings.getByLabel("Nome do projeto").fill("Refúgio da Serra");
  await settings.getByRole("button", { name: "Salvar" }).click();
  await expect(page.getByText("Salvo.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Refúgio da Serra" })).toBeVisible();

  await menu("Refúgio da Serra");
  await page.getByRole("menuitem", { name: "Arquivar projeto" }).click();
  await page.getByRole("alertdialog", { name: "Arquivar “Refúgio da Serra”?" }).getByRole("button", { name: "Arquivar" }).click();
  await expect(page.getByText("Projeto “Refúgio da Serra” arquivado.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Refúgio da Serra" })).toBeHidden();
  await page.getByRole("button", { name: "Desfazer" }).click();
  await expect(page.getByText("Projeto “Refúgio da Serra” restaurado.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Refúgio da Serra" })).toBeVisible();
});

// A36: an owner invites from Configurações → Equipe; the invited person uses the
// link (emailed, or copied from the page) to choose a password, and is in.
test("an owner invites a person, who chooses a password from the link and is in", async ({ page, browser }) => {
  await page.goto(invite("dona-equipe@alinea.example", "owner"));
  await page.getByLabel("Nova senha").fill("senha-escolhida");
  await page.getByLabel("Repita a senha").fill("senha-escolhida");
  await page.getByRole("button", { name: "Salvar senha e entrar" }).click();
  await skipTour(page);
  await page.goto("/painel/configuracoes/equipe");
  await page.getByRole("button", { name: "Convidar pessoa" }).click();
  await page.getByLabel("Nome", { exact: true }).fill("Caio Reis");
  await page.getByLabel("E-mail").fill("caio-equipe@alinea.example");
  await page.getByRole("button", { name: "Enviar convite" }).click();
  const link = await page.getByLabel("Link do convite").inputValue();
  await expect(page.getByRole("list", { name: "Equipe" })).toContainText("Convite pendente");

  // On the office's address, as emailed; this test server listens on its own port.
  const other = await browser.newPage();
  await other.goto(link.replace(/:\d+\//, `:${PORT}/`));
  await other.getByLabel("Nova senha").fill("outra-senha-boa");
  await other.getByLabel("Repita a senha").fill("outra-senha-boa");
  await other.getByRole("button", { name: "Salvar senha e entrar" }).click();
  await expect(other.getByRole("heading", { name: "Projetos" })).toBeVisible();
  await other.close();

  await page.getByRole("button", { name: "Pronto" }).click();
  await page.reload();
  const caio = page.getByRole("list", { name: "Equipe" }).getByRole("listitem").filter({ hasText: "Caio Reis" });
  await expect(caio).toContainText("Equipe");
  await expect(caio).not.toContainText("Convite pendente");
});

test("cards in a row line up, whatever their content", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  const link = invite("alinhamento@alinea.example");
  await page.goto(link);
  await page.getByLabel("Nova senha").fill("senha-escolhida");
  await page.getByLabel("Repita a senha").fill("senha-escolhida");
  await page.getByRole("button", { name: "Salvar senha e entrar" }).click();
  // Apartamento Atlântico — Copacabana wraps to two lines; Casa Jardim doesn't.
  const active = page.getByRole("region", { name: "Em andamento" });
  await expect(active.getByText("Apartamento Atlântico — Copacabana")).toBeVisible();
  // In every row of cards, the "Etapa atual" labels sit at one height.
  const rows = await active.getByTestId("project-card").evaluateAll((cards) => {
    const byRow = new Map<number, number[]>();
    for (const card of cards) {
      const label = [...card.querySelectorAll("*")].find((el) => el.textContent?.trim() === "Etapa atual");
      if (!label) continue; // a project without stages
      const row = Math.round(card.getBoundingClientRect().top);
      byRow.set(row, [...(byRow.get(row) ?? []), Math.round(label.getBoundingClientRect().top)]);
    }
    return [...byRow.values()];
  });
  expect(rows.some((tops) => tops.length > 1)).toBe(true); // at least one row to compare
  for (const tops of rows) expect(new Set(tops).size).toBe(1);
  // And nothing in a card runs into what's under it (a sixth part once pushed the
  // meeting onto the update's line: the card has five rows).
  const overlaps = await active.getByTestId("project-card").evaluateAll((cards) =>
    cards.flatMap((card) => {
      const parts = [...card.children].filter((el) => el.getBoundingClientRect().height > 0 && getComputedStyle(el).position !== "absolute");
      return parts.slice(1).flatMap((part, i) =>
        part.getBoundingClientRect().top < parts[i]!.getBoundingClientRect().bottom - 1 ? [`${card.textContent?.slice(0, 20)}: ${part.className}`] : [],
      );
    }),
  );
  expect(overlaps).toEqual([]);
});

test("the client page: content, redirects, not found and protected", async ({ page }) => {
  // No sign-in: it's the client's page.
  await page.goto("/casa-jardim");
  await expect(page.getByRole("heading", { level: 1, name: "Casa Jardim" })).toHaveText("Casa Jardim"); // capitals by CSS
  await expect(page).toHaveTitle("Casa Jardim · Alinea (dev)");
  await expect(page.getByRole("heading", { name: "Etapas e próximos passos" })).toBeVisible();
  await expect(page.getByText("Apresentação do layout")).toBeVisible();
  // The current stage is open; another opens from the timeline.
  await expect(page.getByText("Levantamento concluído", { exact: false })).toBeHidden();
  await page.getByRole("button", { name: /02\s*Levantamento/ }).click();
  await expect(page.getByText("Levantamento concluído", { exact: false })).toBeVisible();
  // "Sobre esta etapa": the project type's own description.
  await page.getByRole("button", { name: "Sobre esta etapa: Levantamento" }).click();
  await expect(page.getByText("Análise do terreno, medidas, legislação e condicionantes.")).toBeVisible();

  await page.goto("/apto-atlantico");
  await expect(page).toHaveURL(/\/apartamento-atlantico$/);

  const unknown = await page.goto("/nao-existe");
  expect(unknown?.status()).toBe(404);
  await expect(page.getByRole("heading", { name: "Página não encontrada" })).toBeVisible();

  await page.goto("/refugio-da-mantiqueira");
  await expect(page.getByRole("heading", { name: "Página protegida" })).toBeVisible();
  await expect(page.getByText("Mantiqueira")).toHaveCount(0);
});

test("staff open a project's page from its card, and clients see it straight away", async ({ page, browser }) => {
  const link = invite("publicar@alinea.example");
  await page.goto(link);
  await page.getByLabel("Nova senha").fill("senha-escolhida");
  await page.getByLabel("Repita a senha").fill("senha-escolhida");
  await page.getByRole("button", { name: "Salvar senha e entrar" }).click();
  await skipTour(page);

  await page.getByRole("link", { name: "Casa das Oliveiras" }).click();
  await expect(page).toHaveURL(/\/casa-das-oliveiras$/);
  const bar = page.getByRole("navigation", { name: "Ferramentas do escritório" });
  await expect(bar.getByRole("button", { name: "Editar" })).toBeVisible();
  await expect(bar).not.toContainText("Publica"); // no publish step (A35)

  // A visitor (no session) sees it at once.
  const visitor = await browser.newPage();
  expect((await visitor.goto("/casa-das-oliveiras"))?.status()).toBe(200);
  await expect(visitor.getByRole("heading", { level: 1, name: "Casa das Oliveiras" })).toBeVisible();
  await expect(visitor.getByRole("navigation", { name: "Ferramentas do escritório" })).toHaveCount(0);

  await bar.getByRole("link", { name: "Painel" }).click();
  await expect(page.getByRole("heading", { name: "Projetos" })).toBeVisible();
  await visitor.close();
});

test("staff protect a page with a password; a client unlocks it once", async ({ page, browser }) => {
  const link = invite("senha@alinea.example");
  await page.goto(link);
  await page.getByLabel("Nova senha").fill("senha-escolhida");
  await page.getByLabel("Repita a senha").fill("senha-escolhida");
  await page.getByRole("button", { name: "Salvar senha e entrar" }).click();

  await page.getByRole("button", { name: "Opções do projeto Apartamento Atlântico — Copacabana" }).click();
  await page.getByRole("menuitem", { name: "Configurações do projeto" }).click();
  const settings = page.getByRole("dialog", { name: "Projeto" });
  await settings.getByText("Com senha", { exact: true }).click();
  await settings.getByLabel(/^Senha/).fill("praia-123");
  await settings.getByRole("button", { name: "Salvar" }).click();
  await expect(page.getByText("Salvo.")).toBeVisible();

  const client = await browser.newPage();
  await client.goto("/apartamento-atlantico");
  await expect(client.getByRole("heading", { name: "Página protegida" })).toBeVisible();
  await expect(client.getByText("Copacabana")).toHaveCount(0);
  await client.getByLabel("Senha").fill("errada");
  await client.getByRole("button", { name: "Entrar" }).click();
  await expect(client.getByRole("alert")).toContainText("Senha incorreta");
  await client.getByLabel("Senha").fill("praia-123");
  await client.getByRole("button", { name: "Entrar" }).click();
  await expect(client.getByRole("heading", { level: 1, name: "Apartamento Atlântico — Copacabana" })).toBeVisible();
  // Once per device: a reload stays unlocked.
  await client.reload();
  await expect(client.getByRole("heading", { level: 1, name: "Apartamento Atlântico — Copacabana" })).toBeVisible();
  await client.close();
});

test("the client page lists each stage's files, with subfolders as groups", async ({ page }) => {
  await page.goto("/casa-jardim");
  // The current stage (03) is open.
  const current = page.locator("#stage-2");
  await expect(current.getByText("Plantas v2.pdf")).toBeVisible();
  await expect(current.getByText("02 arquivos")).toBeVisible();
  // A file opens its preview; "Salvar" downloads it.
  await current.getByRole("button", { name: "Abrir Implantação.dwg" }).click();
  const preview = page.getByRole("dialog", { name: "Implantação.dwg" });
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    preview.getByRole("button", { name: "Salvar" }).click(),
  ]);
  expect(download.suggestedFilename()).toBe("Implantação.dwg"); // the server's name for it
  await preview.getByRole("button", { name: "Fechar" }).click();
  await expect(page).toHaveURL(/\/casa-jardim$/); // the page stays

  await page.getByRole("button", { name: /01\s*Briefing/ }).click();
  const first = page.locator("#stage-0");
  await expect(first.getByText("Programa de necessidades.pdf")).toBeVisible();
  await expect(first.getByRole("heading", { name: "Levantamento" })).toBeVisible(); // a subfolder
  await expect(first.getByText("Medidas do terreno.pdf")).toBeVisible();
});

test("staff upload a file into a stage, the client sees it, and staff hide it", async ({ page, browser }) => {
  const link = invite("arquivos@alinea.example");
  await page.goto(link);
  await page.getByLabel("Nova senha").fill("senha-escolhida");
  await page.getByLabel("Repita a senha").fill("senha-escolhida");
  await page.getByRole("button", { name: "Salvar senha e entrar" }).click();
  await skipTour(page);
  await page.getByRole("heading", { name: "Projetos" }).waitFor();

  await page.goto("/casa-jardim");
  await page.getByRole("navigation", { name: "Ferramentas do escritório" }).getByRole("button", { name: "Editar" }).click();
  await page.getByRole("button", { name: /01\s*Briefing/ }).click();
  const briefing = page.locator("#stage-0");
  await briefing.getByLabel("escolha no computador").setInputFiles({
    name: "Levantamento fotográfico.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4 fotos"),
  });
  await expect(page.getByText("Arquivo enviado.")).toBeVisible();
  await expect(briefing.getByText("Levantamento fotográfico.pdf")).toBeVisible();

  const client = await browser.newPage();
  await client.goto("/casa-jardim");
  await client.getByRole("button", { name: /01\s*Briefing/ }).click();
  await expect(client.locator("#stage-0").getByText("Levantamento fotográfico.pdf")).toBeVisible();

  await briefing.getByRole("button", { name: "Ações para Levantamento fotográfico.pdf" }).click();
  await page.getByRole("menuitem", { name: /Ocultar do cliente/ }).click();
  await expect(page.getByText(/não aparece mais para o cliente/)).toBeVisible();
  await client.close();
  // A new visitor (a returning one may keep the list up to two minutes, A10).
  const later = await browser.newPage();
  await later.goto("/casa-jardim");
  await later.getByRole("button", { name: /01\s*Briefing/ }).click();
  await expect(later.locator("#stage-0").getByText("Programa de necessidades.pdf")).toBeVisible();
  await expect(later.locator("#stage-0").getByText("Levantamento fotográfico.pdf")).toHaveCount(0);
  await later.close();
});

test("staff edit the page in place and the client sees it", async ({ page, browser }) => {
  const link = invite("editar@alinea.example");
  await page.goto(link);
  await page.getByLabel("Nova senha").fill("senha-escolhida");
  await page.getByLabel("Repita a senha").fill("senha-escolhida");
  await page.getByRole("button", { name: "Salvar senha e entrar" }).click();
  await skipTour(page);
  await page.getByRole("heading", { name: "Projetos" }).waitFor();

  await page.goto("/casa-jardim");
  const bar = page.getByRole("navigation", { name: "Ferramentas do escritório" });
  await bar.getByRole("button", { name: "Editar" }).click();

  await page.getByRole("button", { name: "Editar descrição" }).click();
  await page.getByLabel("Descrição").fill("Casa revisada.\n- Pátio com jabuticabeira");
  await page.getByRole("button", { name: "Salvar" }).click();
  await expect(page.getByText("Salvo.")).toBeVisible();

  // "Recado para o cliente" opens the stage's "Editar etapa".
  await page.locator("#stage-2").getByRole("button", { name: "Recado para o cliente" }).click();
  await page.getByLabel("Recado da etapa").fill("Confira as plantas v2 antes de sexta.");
  await page.locator("#stage-2").getByRole("button", { name: "Salvar" }).click();
  await expect(page.locator("#stage-2").getByText("Confira as plantas v2 antes de sexta.")).toBeVisible();

  // A cover added from the page: "Trocar capa" and "Remover capa" side by side on it,
  // each readable, then removed again.
  const [chooser] = await Promise.all([
    page.waitForEvent("filechooser"),
    page.getByRole("button", { name: /Adicionar foto de capa/ }).click(),
  ]);
  await chooser.setFiles({ name: "obra.png", mimeType: "image/png", buffer: PNG_1PX });
  await page.getByRole("dialog", { name: "Ajustar a capa" }).getByRole("button", { name: "Usar recorte" }).click();
  const change = page.getByRole("button", { name: "Trocar capa" });
  const remove = page.getByRole("button", { name: "Remover capa" });
  await expect(change).toBeVisible();
  const [a, b] = [(await change.boundingBox())!, (await remove.boundingBox())!];
  expect(a.x + a.width <= b.x || b.x + b.width <= a.x).toBe(true);
  const contrast = await change.evaluate((button) => {
    const style = getComputedStyle(button);
    return style.color !== style.backgroundColor;
  });
  expect(contrast).toBe(true);
  await remove.click();
  await expect(page.getByRole("button", { name: /Adicionar foto de capa/ })).toBeVisible();

  const client = await browser.newPage();
  await client.goto("/casa-jardim");
  await expect(client.getByText("Casa revisada.")).toBeVisible();
  await expect(client.getByText("Pátio com jabuticabeira")).toBeVisible();
  await expect(client.locator("#stage-2").getByText("Confira as plantas v2 antes de sexta.")).toBeVisible();
  await expect(client.getByRole("button", { name: "Editar descrição" })).toHaveCount(0);
  await client.close();
});

test("staff rename, add and remove stages, and advance the project", async ({ page, browser }) => {
  const link = invite("etapas@alinea.example");
  await page.goto(link);
  await page.getByLabel("Nova senha").fill("senha-escolhida");
  await page.getByLabel("Repita a senha").fill("senha-escolhida");
  await page.getByRole("button", { name: "Salvar senha e entrar" }).click();
  await skipTour(page);
  await page.getByRole("heading", { name: "Projetos" }).waitFor();

  // (Casa Jardim: earlier tests password-protect the apartment.)
  await page.goto("/casa-jardim");
  const bar = page.getByRole("navigation", { name: "Ferramentas do escritório" });
  await bar.getByRole("button", { name: "Editar" }).click();

  // Rename the second stage.
  await page.getByRole("button", { name: "Editar etapa Levantamento" }).click();
  await page.getByLabel("Nome da etapa").fill("Medição do apartamento");
  await page.locator("#stage-1").getByRole("button", { name: "Salvar" }).click();
  await expect(page.locator("#st-1")).toHaveText("Medição do apartamento");

  // Add the office's own stage, then remove it.
  await page.getByRole("button", { name: "+ Adicionar etapa" }).click();
  await page.getByLabel("Ou uma etapa do escritório").fill("Visita técnica");
  await page.getByRole("button", { name: "Adicionar", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Visita técnica" })).toBeVisible();
  await page.getByRole("button", { name: "Editar etapa Visita técnica" }).click();
  await page.getByRole("button", { name: "Remover etapa", exact: true }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Remover", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Visita técnica" })).toHaveCount(0);

  // Finish the current stage: the client sees the next one in progress.
  await page.getByRole("button", { name: "Marcar etapa como concluída" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Concluir etapa" }).click(); // asked first
  await expect(page.getByText(/Etapa atual: “/)).toBeVisible(); // the toast
  const client = await browser.newPage();
  await client.goto("/casa-jardim");
  await expect(client.locator("#stage-3 .pill--current")).toBeVisible();
  await expect(client.getByText("Medição do apartamento").first()).toBeVisible();
  await client.close();
});

test("staff drag a stage to a new place, and the new order is saved", async ({ page }) => {
  const link = invite("ordem@alinea.example");
  await page.goto(link);
  await page.getByLabel("Nova senha").fill("senha-escolhida");
  await page.getByLabel("Repita a senha").fill("senha-escolhida");
  await page.getByRole("button", { name: "Salvar senha e entrar" }).click();
  await skipTour(page);
  await page.getByRole("heading", { name: "Projetos" }).waitFor();

  // A project no other test reorders.
  await page.goto("/refugio-da-mantiqueira");
  await page.getByRole("navigation", { name: "Ferramentas do escritório" }).getByRole("button", { name: "Editar" }).click();
  // The titles as stored (the page shows them in capitals).
  const first = (await page.locator("#st-0").textContent())!;
  const second = (await page.locator("#st-1").textContent())!;
  await page.getByRole("button", { name: "Reordenar etapas" }).click();
  const list = page.getByRole("dialog", { name: "Reordenar etapas" });
  // Drag the first stage's handle below the second, in small steps as a hand would.
  const handle = (await list.getByRole("button", { name: `Arrastar ${first}` }).boundingBox())!;
  const target = (await list.getByRole("button", { name: `Arrastar ${second}` }).boundingBox())!;
  await page.mouse.move(handle.x + handle.width / 2, handle.y + handle.height / 2);
  await page.mouse.down();
  await page.mouse.move(target.x + target.width / 2, target.y + target.height / 2 + 12, { steps: 12 });
  await page.mouse.up();
  await expect(list.locator("li").first()).toContainText(second);
  // The drag library swallows a click in the instant after a drop (so the dropped
  // row isn't also clicked); a hand is never that quick, the test is.
  await page.waitForTimeout(300);
  await list.getByRole("button", { name: "Salvar" }).click();
  await expect(page.getByText("Ordem das etapas salva.")).toBeVisible();
  await expect(page.locator("#st-0")).toHaveText(second);

  await page.reload(); // as the server has it (its client page has a password)
  await expect(page.locator("#st-0")).toHaveText(second);
  await expect(page.locator("#st-1")).toHaveText(first);
});

test("a new staff member's first project page shows the tour once; \"?\" replays it", async ({ page }) => {
  const link = invite("tour@alinea.example");
  await page.goto(link);
  await page.getByLabel("Nova senha").fill("senha-escolhida");
  await page.getByLabel("Repita a senha").fill("senha-escolhida");
  await page.getByRole("button", { name: "Salvar senha e entrar" }).click();
  await page.getByRole("heading", { name: "Projetos" }).waitFor();

  await page.goto("/casa-jardim");
  const popover = page.locator(".driver-popover");
  await expect(popover).toContainText("Ver como cliente e Editar");
  // Every step, upload area included (its part loads separately): 5 of them.
  await expect(popover).toContainText("1 de 5");
  await popover.getByRole("button", { name: /Próximo/ }).click();
  await expect(popover).toContainText("Editar cada seção");
  // The tour runs in edit mode, where its steps' parts are.
  const bar = page.getByRole("navigation", { name: "Ferramentas do escritório" });
  await expect(bar.getByRole("button", { name: "Editar" })).toHaveAttribute("aria-pressed", "true");
  const seen = page.waitForResponse((r) => r.url().endsWith("/api/me/tour-seen"));
  await page.keyboard.press("Escape"); // closed early: seen all the same
  await expect(popover).toHaveCount(0);
  expect((await seen).status()).toBe(204);

  await page.reload();
  await bar.waitFor();
  await page.waitForTimeout(800);
  await expect(popover).toHaveCount(0); // not again, for this account
  await bar.getByRole("button", { name: "Ver o tour da página" }).click();
  await expect(popover).toContainText("Ver como cliente e Editar");
});

test("on a phone the staff bar holds all its buttons", async ({ page }) => {
  const link = invite("phonebar@alinea.example");
  await page.goto(link);
  await page.getByLabel("Nova senha").fill("senha-escolhida");
  await page.getByLabel("Repita a senha").fill("senha-escolhida");
  await page.getByRole("button", { name: "Salvar senha e entrar" }).click();
  await skipTour(page);

  for (const width of [390, 375, 360]) {
    await page.setViewportSize({ width, height: 800 });
    await page.goto("/casa-jardim");
    const bar = page.getByRole("navigation", { name: "Ferramentas do escritório" });
    await expect(bar.getByRole("button", { name: "Ver o tour da página" })).toBeVisible();
    const box = (await bar.boundingBox())!;
    for (const control of await bar.locator(":scope > a, :scope > button, :scope > .seg button").all()) {
      const inner = (await control.boundingBox())!;
      expect(inner.x, `${width}px`).toBeGreaterThanOrEqual(box.x);
      expect(inner.x + inner.width, `${width}px`).toBeLessThanOrEqual(box.x + box.width);
    }
    await expect(bar.getByRole("link", { name: "Painel" })).toBeVisible(); // named even when only the arrow shows
    if (width >= 375) {
      // Room for the whole label: cut short ("…") only on narrower phones.
      const label = bar.getByRole("button", { name: "Ver como cliente" });
      expect(await label.evaluate((b) => b.scrollWidth <= b.clientWidth), `${width}px`).toBe(true);
    }
  }
});

// The project page on a phone: nothing a person can see runs past the screen's
// edge, as the client sees it and in edit mode (Fabio, 22 Oct 2026: "no sideways
// scrolling"). A panel that is closed (invisible) doesn't count.
test("on a phone nothing on the project page is wider than the screen", async ({ page }) => {
  const link = invite("phonewidth@alinea.example");
  await page.goto(link);
  await page.getByLabel("Nova senha").fill("senha-escolhida");
  await page.getByLabel("Repita a senha").fill("senha-escolhida");
  await page.getByRole("button", { name: "Salvar senha e entrar" }).click();
  await skipTour(page);
  await page.setViewportSize({ width: 360, height: 800 });
  await page.goto("/casa-jardim");
  const bar = page.getByRole("navigation", { name: "Ferramentas do escritório" });
  const tooWide = () =>
    page.evaluate(() => {
      const edge = document.documentElement.clientWidth;
      const seen = (el: Element) => {
        for (let at: Element | null = el; at; at = at.parentElement) {
          const style = getComputedStyle(at);
          if (style.visibility === "hidden" || style.opacity === "0" || style.display === "none") return false;
          // A closed <details> draws only its summary.
          const parent = at.parentElement;
          if (parent instanceof HTMLDetailsElement && !parent.open && at.tagName !== "SUMMARY") return false;
        }
        return true;
      };
      return [...document.querySelectorAll(".client *")]
        .filter((el) => el.getBoundingClientRect().width > 0 && el.getBoundingClientRect().right > edge + 1 && seen(el))
        .map((el) => `${el.tagName.toLowerCase()}.${String(el.getAttribute("class"))}`);
    });
  await bar.getByRole("button", { name: "Ver como cliente" }).click();
  expect(await tooWide()).toEqual([]);
  await bar.getByRole("button", { name: "Editar", exact: true }).click();
  await expect(page.getByRole("button", { name: "Marcar etapa como concluída" })).toBeVisible();
  expect(await tooWide()).toEqual([]);
  // The check itself: something too wide is caught.
  await page.evaluate(() => {
    const wide = document.createElement("div");
    wide.className = "too-wide";
    wide.style.width = "600px";
    document.querySelector(".cwrap")!.append(wide);
  });
  expect(await tooWide()).toContain("div.too-wide");
});

// Counts are round, like the painel's tabs; the client page's straight edges had
// squared the updates bell's.
test("the updates bell's count is round, on a computer and a phone", async ({ page }) => {
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/tour-projeto"); // the example project has unread updates
    const count = page.locator(".client-notifications .notification-count");
    await count.waitFor();
    const { radius, height } = await count.evaluate((el) => ({
      radius: parseFloat(getComputedStyle(el).borderTopLeftRadius),
      height: el.getBoundingClientRect().height,
    }));
    expect(radius).toBeGreaterThanOrEqual(height / 2);
  }
});

test("the example project: from the painel, its own tour, and edits that never leave the browser", async ({ page }) => {
  const link = invite("exemplo@alinea.example");
  await page.goto(link);
  await page.getByLabel("Nova senha").fill("senha-escolhida");
  await page.getByLabel("Repita a senha").fill("senha-escolhida");
  await page.getByRole("button", { name: "Salvar senha e entrar" }).click();
  await page.getByRole("heading", { name: "Projetos" }).waitFor();
  const writes: string[] = [];
  page.on("request", (r) => r.method() !== "GET" && r.url().includes("/api/") && writes.push(r.url()));

  await page.getByRole("link", { name: /Ver o exemplo/ }).click(); // the invitation above Primeiros passos
  await expect(page).toHaveURL(/\/tour-projeto$/);
  // Its own tour, in the client's view; not the setup tour this new account hasn't seen.
  const popover = page.locator(".driver-popover");
  await expect(popover).toContainText("O nome e o tipo do projeto");
  await popover.getByRole("button", { name: "Pular" }).click();
  await expect(popover).toHaveCount(0);

  const bar = page.getByRole("navigation", { name: "Ferramentas do escritório" });
  await bar.getByRole("button", { name: "Editar" }).click();
  await page.getByRole("button", { name: "Editar descrição" }).click();
  await page.getByLabel("Descrição").fill("Uma casa só nossa.");
  await page.getByRole("button", { name: "Salvar" }).click();
  await expect(page.getByText("Uma casa só nossa.")).toBeVisible();
  expect(writes).toEqual([]); // nothing reached the server

  // A new visit: as it was, and the tour again.
  await page.reload();
  await expect(popover).toContainText("O nome e o tipo do projeto");
  await expect(page.getByText("Uma casa só nossa.")).toHaveCount(0);
});

test("the preview page: the client page in a frame, changed live from the panel and kept in the address", async ({ page }) => {
  const asked: string[] = [];
  page.on("request", (r) => r.url().includes("/api/") && asked.push(r.url()));
  await page.goto("/painel/previa?width=phone&meeting=long");
  const frame = page.frameLocator("iframe");
  await expect(frame.getByText(/Apresentação do estudo preliminar/).locator("visible=true")).toBeVisible();
  expect(await page.locator("iframe").evaluate((el) => el.getBoundingClientRect().width)).toBe(390);
  await expect(frame.getByRole("navigation", { name: "Ferramentas do escritório" })).toHaveCount(0);

  await page.getByRole("radio", { name: "Equipe" }).check();
  await page.getByRole("radio", { name: "Escuro" }).check();
  await expect(frame.getByRole("navigation", { name: "Ferramentas do escritório" })).toBeVisible();
  expect(await page.frames()[1]!.evaluate(() => document.documentElement.dataset.theme)).toBe("dark");

  // The page's own theme switch (its header menu, as on the painel): the panel and
  // the address follow, and the device's own choice for the real pages is left as it was.
  await frame.getByRole("button", { name: /^(Sua conta|Menu)$/ }).locator("visible=true").first().click();
  await frame.getByRole("menuitemcheckbox", { name: "Modo escuro" }).click();
  await expect(page.getByRole("radio", { name: "Claro" })).toBeChecked();
  expect(page.url()).not.toContain("theme=");
  expect(await page.evaluate(() => localStorage.getItem("theme"))).toBeNull();
  await page.getByRole("radio", { name: "Escuro" }).check();

  // A link reproduces the combination.
  await page.reload();
  await expect(page.getByRole("radio", { name: "Equipe" })).toBeChecked();
  await expect(frame.getByRole("navigation", { name: "Ferramentas do escritório" })).toBeVisible();
  expect(asked).toEqual([]); // nothing reached the server
});

/** Opens Casa Jardim's third stage, the one with files (earlier tests may have
 *  moved the current stage on). */
async function openThirdStage(page: Page) {
  const stage = page.locator("#stage-2");
  // From the timeline, as in edit mode (where the stage's own arrow gives way to its controls).
  if (!/is-expanded/.test((await stage.getAttribute("class")) ?? ""))
    await page.getByRole("list", { name: "Etapas" }).getByRole("button", { name: /^03 / }).click();
  await page.locator("#stage-2.is-expanded .file").first().waitFor();
  await page.waitForTimeout(400); // the opening's fade
}

/** How far the open stage's body is from its content's height (0: a fit). */
async function openStageMisfit(page: Page): Promise<number> {
  return page.evaluate(() => {
    const body = document.querySelector<HTMLElement>(".stage.is-expanded .stage__body")!;
    const px = (el: Element, side: "paddingBottom" | "marginBottom" | "borderBottomWidth") => parseFloat(getComputedStyle(el)[side]);
    const inner = body.querySelector<HTMLElement>(".stage__body-inner")!;
    const last = inner.lastElementChild!;
    // From the body's top to the last thing in it, with what sits under that.
    const content =
      last.getBoundingClientRect().bottom + px(last, "marginBottom") + px(inner, "paddingBottom") + px(inner, "borderBottomWidth") +
      px(body, "paddingBottom") - body.getBoundingClientRect().top;
    return Math.abs(body.getBoundingClientRect().height - content);
  });
}

// Safari once sized an open stage far taller than its files, and in edit mode too
// short, files spilling out (the prototype's 0fr → 1fr opening).
test("an open stage is as tall as its files, for clients and in edit mode @safari", async ({ page }, info) => {
  await page.goto("/casa-jardim");
  await openThirdStage(page);
  expect(await openStageMisfit(page)).toBeLessThan(3);

  await page.goto(invite(`altura-${info.project.name}@alinea.example`));
  await page.getByLabel("Nova senha").fill("senha-escolhida");
  await page.getByLabel("Repita a senha").fill("senha-escolhida");
  await page.getByRole("button", { name: "Salvar senha e entrar" }).click();
  await skipTour(page);
  await page.goto("/casa-jardim");
  await page.getByRole("navigation", { name: "Ferramentas do escritório" }).getByRole("button", { name: "Editar" }).click();
  await openThirdStage(page);
  await page.locator("#stage-2 .drop").waitFor();
  expect(await openStageMisfit(page)).toBeLessThan(3);
});

/** What, in the page, covers parts of the popup: nothing, when it's on top. */
async function coveringPopup(page: Page, selector: string): Promise<string[]> {
  return page.evaluate((selector) => {
    const popup = document.querySelector<HTMLElement>(selector)!;
    popup.scrollIntoView({ block: "center" });
    const box = popup.getBoundingClientRect();
    const covers = new Set<string>();
    for (let x = 0.05; x < 1; x += 0.15)
      for (let y = 0.05; y < 1; y += 0.15) {
        const top = document.elementFromPoint(box.left + box.width * x, box.top + box.height * y);
        if (top && !popup.contains(top)) covers.add(`${top.tagName.toLowerCase()}.${[...top.classList].join(".")}`);
      }
    return [...covers];
  }, selector);
}

async function signInAsNewStaff(page: Page, email: string) {
  await page.goto(invite(email));
  await page.getByLabel("Nova senha").fill("senha-escolhida");
  await page.getByLabel("Repita a senha").fill("senha-escolhida");
  await page.getByRole("button", { name: "Salvar senha e entrar" }).click();
  await skipTour(page);
}

// Each stage is its own layer, and later stages paint over earlier ones: a popup
// reaching past its stage's edge used to go under the next stage (on a phone, a
// file's menu always does), and an open menu under the other files' "⋯" buttons.
test("a file's open menu is above the other files and the next stage, on a phone @safari", async ({ page }, info) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signInAsNewStaff(page, `menu-arquivo-${info.project.name}@alinea.example`);
  await page.goto("/casa-jardim");
  // A phone has no timeline: the stage opens from its own arrow, before edit mode
  // (where the arrow gives way to the stage's controls).
  const third = page.locator("#stage-2");
  if (!/is-expanded/.test((await third.getAttribute("class")) ?? "")) await third.locator('[aria-controls="stage-body-2"]').click();
  await page.getByRole("navigation", { name: "Ferramentas do escritório" }).getByRole("button", { name: "Editar" }).click();
  await page.locator("#stage-2.is-expanded .file").first().waitFor();
  await page.waitForTimeout(400); // the opening's fade
  await third.getByRole("button", { name: /^Ações para / }).first().click();
  await page.locator("#stage-2 .filemenu.is-open [role=menuitem]").first().waitFor();
  await page.waitForTimeout(300); // the menu's rise
  expect(await coveringPopup(page, "#stage-2 .filemenu.is-open .menu__list")).toEqual([]);
});

test("\"Sobre esta etapa\" is above the stages after it @safari", async ({ page }, info) => {
  await signInAsNewStaff(page, `sobre-etapa-${info.project.name}@alinea.example`);
  await page.goto("/casa-jardim");
  await page.locator("#stage-0 .stage-help-toggle").click();
  await page.waitForTimeout(300);
  expect(await coveringPopup(page, "#stage-0 .stage-help-pop:not([hidden])")).toEqual([]);
});

// Edit mode hides "Sobre esta etapa" but may leave it open: its stage mustn't stay
// raised, level with the stage whose file menu is open (the later one would win).
test("in edit mode only the stage with the open file menu is raised", async ({ page }) => {
  await signInAsNewStaff(page, "menu-e-sobre@alinea.example");
  await page.goto("/casa-jardim");
  const later = page.locator(".stage-help-toggle").last();
  await later.click();
  await page.getByRole("navigation", { name: "Ferramentas do escritório" }).getByRole("button", { name: "Editar" }).click();
  await openThirdStage(page);
  await page.locator("#stage-2").getByRole("button", { name: /^Ações para / }).first().click();
  await page.locator("#stage-2 .filemenu.is-open [role=menuitem]").first().waitFor();
  const raised = await page.evaluate(() =>
    [...document.querySelectorAll<HTMLElement>(".stage")].filter((stage) => getComputedStyle(stage).zIndex === "3").map((stage) => stage.id),
  );
  expect(raised).toEqual(["stage-2"]);
});

// A file's "⋯" looks tag-sized over its thumbnail but is tapped like an icon
// button (ui/sizes.css): a tap just outside its circle still opens it.
test("a file's \"⋯\" is small to look at and icon-sized to tap", async ({ page }) => {
  await page.goto(invite("menu-alvo@alinea.example"));
  await page.getByLabel("Nova senha").fill("senha-escolhida");
  await page.getByLabel("Repita a senha").fill("senha-escolhida");
  await page.getByRole("button", { name: "Salvar senha e entrar" }).click();
  await skipTour(page);
  await page.goto("/casa-jardim");
  await page.getByRole("navigation", { name: "Ferramentas do escritório" }).getByRole("button", { name: "Editar" }).click();
  await openThirdStage(page);
  const button = page.locator("#stage-2").getByRole("button", { name: /^Ações para / }).first();
  await button.scrollIntoViewIfNeeded();
  const box = (await button.boundingBox())!;
  expect(Math.round(box.height)).toBe(24);
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2 + 15); // 3px below the circle
  await expect(page.locator("#stage-2 .filemenu.is-open")).toHaveCount(1);
});

// Plan section 16: "?" in the painel's top bar runs the painel tour; its last
// step opens the example project, whose own tour starts there.
test("the painel tour, from \"?\", ends at the example project and its tour", async ({ page }) => {
  await page.goto(invite("tour-painel@alinea.example"));
  await page.getByLabel("Nova senha").fill("senha-escolhida");
  await page.getByLabel("Repita a senha").fill("senha-escolhida");
  await page.getByRole("button", { name: "Salvar senha e entrar" }).click();
  await skipTour(page);
  const popover = page.locator(".driver-popover");
  await expect(popover).toHaveCount(0); // never on its own
  await page.getByRole("button", { name: "Ver o tour do painel" }).click();
  await expect(popover).toBeVisible();
  for (let i = 0; i < 6 && (await popover.getByRole("button", { name: "Próximo" }).count()); i++)
    await popover.getByRole("button", { name: "Próximo" }).click();
  await expect(popover).toContainText("Um projeto de exemplo");
  await popover.getByRole("button", { name: "Ver o exemplo" }).click();
  await expect(page).toHaveURL(/\/tour-projeto$/);
  await expect(page.locator(".driver-popover")).toContainText("O nome e o tipo do projeto");
});
