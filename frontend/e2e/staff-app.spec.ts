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
  await page.goto("/painel/um/endereco/qualquer");
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

  await dialog.getByLabel("Endereço da página").fill("casa-jardim-teste");
  await dialog.getByText("Interiores", { exact: true }).click();
  await expect(dialog.getByRole("radio", { name: /Interiores/ })).toBeChecked();
  await dialog.getByRole("button", { name: "Criar projeto" }).click();
  await expect(dialog).toBeHidden();

  const drafts = page.getByRole("region", { name: "Rascunhos" });
  const card = drafts.getByTestId("project-card").filter({ hasText: "Família Teste" });
  await expect(card).toContainText("Rascunho");
  await expect(card).toContainText("1 / 6");

  // Search ignores accents and case.
  await page.getByRole("searchbox", { name: "Buscar projetos" }).fill("familia teste");
  await expect(page.getByTestId("project-card")).toHaveCount(1);
  await page.getByRole("searchbox", { name: "Buscar projetos" }).fill("nada parecido");
  await expect(page.getByText("Nenhum projeto encontrado")).toBeVisible();
});
