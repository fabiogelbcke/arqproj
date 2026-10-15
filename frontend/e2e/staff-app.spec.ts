import { execFileSync } from "node:child_process";

import { expect, test } from "@playwright/test";

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
  return link.replace(":8000/", `:${PORT}/`);
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
