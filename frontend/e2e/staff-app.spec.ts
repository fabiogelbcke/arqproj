import { execFileSync } from "node:child_process";

import { expect, test } from "@playwright/test";

// The staff app runs under a strict Content Security Policy (plan section 4).
// Anything the build needs that the policy blocks shows up as a console error.
test.beforeEach(({ page }) => {
  page.on("console", (message) => {
    if (/Content Security Policy/i.test(message.text())) throw new Error(message.text());
  });
});

import { E2E_ENV, PORT } from "../playwright.config";

/** An account made the real way, with the staff command; returns its invite link. */
function invite(email: string): string {
  const output = execFileSync(
    "uv",
    ["run", "python", "-m", "backend.commands.staff", "add", "--tenant", "alinea", "--email", email, "--name", "Teste"],
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

  await page.getByRole("button", { name: "Sair" }).click();
  await expect(page.getByRole("heading", { name: "Entrar" })).toBeVisible();
  await page.goto("/painel");
  await expect(page).toHaveURL(/\/painel\/entrar/); // signed out for real

  await page.getByLabel("E-mail").fill("teste@alinea.example");
  await page.getByLabel("Senha").fill("senha errada");
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page.getByRole("alert")).toContainText("E-mail ou senha incorretos.");
  await expect(page.getByRole("alert")).toContainText("Código de suporte:");

  await page.getByLabel("Senha").fill("senha-escolhida");
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page.getByRole("heading", { name: "Projetos" })).toBeVisible();

  // The invite link was spent.
  await page.goto(link);
  await expect(page.getByRole("heading", { name: "Este link não funciona mais" })).toBeVisible();
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

  const drafts = page.getByRole("region", { name: "Rascunhos" });
  const card = drafts.getByTestId("project-card").filter({ hasText: "Família Teste" });
  await expect(card).toContainText("Rascunho");
  await expect(card).toContainText("1 / 6");
  await expect(card).toContainText("Projeto de Interiores");

  // Search ignores accents and case.
  await page.getByRole("searchbox", { name: "Buscar projetos" }).fill("familia teste");
  await expect(page.getByTestId("project-card")).toHaveCount(1);
  await page.getByRole("searchbox", { name: "Buscar projetos" }).fill("nada parecido");
  await expect(page.getByText("Nenhum projeto encontrado")).toBeVisible();
});

// A real 1×1 PNG, so the browser can preview it.
const PNG_1PX = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
  "base64",
);

test("project settings: rename and cover photo together, archive and undo", async ({ page }) => {
  const link = invite("ajustes@alinea.example");
  await page.goto(link);
  await page.getByLabel("Nova senha").fill("senha-escolhida");
  await page.getByLabel("Repita a senha").fill("senha-escolhida");
  await page.getByRole("button", { name: "Salvar senha e entrar" }).click();

  // A completed project: open its group, then the card's pencil.
  await page.getByRole("button", { name: "Concluídos" }).click();
  await page.getByRole("button", { name: "Editar o projeto Refúgio da Mantiqueira" }).click();
  const settings = page.getByRole("dialog", { name: "Projeto" });
  await settings.getByLabel("Nome do projeto").fill("Refúgio da Serra");
  await settings.locator('input[type="file"]').setInputFiles({ name: "obra.png", mimeType: "image/png", buffer: PNG_1PX });
  await expect(settings.getByRole("img", { name: "Prévia da nova capa" })).toBeVisible();
  await settings.getByRole("button", { name: "Salvar" }).click();
  await expect(page.getByText("Salvo.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Refúgio da Serra" })).toBeVisible();

  // The cover was saved: the dialog now offers to change or remove it.
  await page.getByRole("button", { name: "Editar o projeto Refúgio da Serra" }).click();
  await expect(settings.getByRole("button", { name: "Remover capa" })).toBeVisible();
  await settings.getByRole("button", { name: "Arquivar" }).click();
  await expect(page.getByText("Projeto “Refúgio da Serra” arquivado.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Refúgio da Serra" })).toBeHidden();
  await page.getByRole("button", { name: "Desfazer" }).click();
  await expect(page.getByText("Projeto “Refúgio da Serra” de volta.")).toBeVisible();
  await page.getByRole("button", { name: "Concluídos" }).click(); // its group, folded again
  await expect(page.getByRole("heading", { name: "Refúgio da Serra" })).toBeVisible();
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
  await expect(active.getByTestId("project-card")).toHaveCount(2);
  const tops = await active.getByText("Etapa atual").evaluateAll((labels) =>
    labels.map((label) => Math.round(label.getBoundingClientRect().top)),
  );
  expect(tops.length).toBe(2);
  expect(new Set(tops).size).toBe(1);
});

test("the client page: content, redirects, not found and protected", async ({ page }) => {
  // No sign-in: it's the client's page.
  await page.goto("/casa-jardim");
  await expect(page.getByRole("heading", { level: 1, name: "Casa Jardim" })).toHaveText("/casajardim");
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

  const draft = await page.goto("/casa-das-oliveiras");
  expect(draft?.status()).toBe(404);
  await expect(page.getByRole("heading", { name: "Página não encontrada" })).toBeVisible();

  await page.goto("/refugio-da-mantiqueira");
  await expect(page.getByRole("heading", { name: "Página protegida" })).toBeVisible();
  await expect(page.getByText("Mantiqueira")).toHaveCount(0);
});

test("staff open a draft's page from its card, publish it, and clients can see it", async ({ page, browser }) => {
  const link = invite("publicar@alinea.example");
  await page.goto(link);
  await page.getByLabel("Nova senha").fill("senha-escolhida");
  await page.getByLabel("Repita a senha").fill("senha-escolhida");
  await page.getByRole("button", { name: "Salvar senha e entrar" }).click();

  await page.getByRole("link", { name: "Casa das Oliveiras" }).click();
  await expect(page).toHaveURL(/\/casa-das-oliveiras$/);
  const bar = page.getByRole("navigation", { name: "Ferramentas do escritório" });
  await expect(bar).toContainText("Rascunho, só você vê");

  // A visitor (no session) can't see the draft yet.
  const visitor = await browser.newPage();
  expect((await visitor.goto("/casa-das-oliveiras"))?.status()).toBe(404);

  await bar.getByRole("button", { name: "Publicar" }).click();
  await expect(page.getByText("Publicado. O cliente já pode abrir o link.")).toBeVisible();
  await expect(bar).toContainText("Publicado");

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

  await page.getByRole("button", { name: "Editar o projeto Apartamento Atlântico — Copacabana" }).click();
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
  const dwg = current.getByRole("link", { name: "Baixar Implantação.dwg" });
  await expect(dwg).toHaveAttribute("download", "Implantação.dwg");
  const [download] = await Promise.all([page.waitForEvent("download"), dwg.click()]);
  expect(download.suggestedFilename()).toBe("Implantação.dwg");

  await page.getByRole("button", { name: /01\s*Briefing/ }).click();
  const first = page.locator("#stage-0");
  await expect(first.getByText("Programa de necessidades.pdf")).toBeVisible();
  await expect(first.getByRole("heading", { name: "Levantamento" })).toBeVisible(); // a subfolder
  await expect(first.getByText("Medidas do terreno.pdf")).toBeVisible();
});
