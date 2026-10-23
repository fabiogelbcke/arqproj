import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fakeApi, ME, renderAt, TENANT } from "../test/render";
import * as imageCrop from "../ui/imageCrop";
import type { ProjectSummary } from "./projects";

// The browser's image decoding and canvas aren't in the test DOM: a 4000×3000 photo.
vi.mock("../ui/imageCrop", async (original) => ({
  ...(await original<typeof import("../ui/imageCrop")>()),
  loadImage: vi.fn(async () => ({ naturalWidth: 4000, naturalHeight: 3000 }) as HTMLImageElement),
  cropToFile: vi.fn(async (_image: unknown, _box: unknown, output: { type: string }, name: string) => new File(["x"], name, { type: output.type })),
}));

/** A photo chosen from the card's menu and cropped to 3:2 ("Usar recorte"). */
async function chooseCover() {
  const input = (await screen.findByTestId("project-card")).querySelector('input[type="file"]') as HTMLInputElement;
  await userEvent.upload(input, new File(["jpg"], "obra.jpg", { type: "image/jpeg" }));
  const crop = await screen.findByRole("dialog", { name: "Ajustar a capa" });
  await userEvent.click(await within(crop).findByRole("button", { name: "Usar recorte" }));
  await waitFor(() => expect(screen.queryByRole("dialog", { name: "Ajustar a capa" })).toBeNull());
  expect(imageCrop.cropToFile).toHaveBeenLastCalledWith(expect.anything(), expect.anything(), imageCrop.COVER_OUTPUT, "capa.jpg");
}

const LOCAL = { kind: "folder", writer_status: "none", reader_status: "unknown", account_email: null, folder_url: null, can_manage: true };
const CASA: ProjectSummary = {
  id: "11111111-1111-1111-1111-111111111111",
  name: "Casa Jardim",
  client_name: "Família Oliveira",
  slug: "casa-jardim",
  status: "active",
  project_type: "architecture",
  project_type_label: "Projeto Arquitetônico",
  stage_count: 7,
  completed_stage_count: 2,
  next_meeting: null,
  created_at: "2026-09-01T12:00:00Z",
  last_activity_at: null,
  row_version: 4,
  cover_url: null,
  access_mode: "public",
  recipients: [],
};
const PATH = `/api/projects/${CASA.id}`;

function api(extra = {}) {
  return fakeApi({
    "GET /api/tenant": () => ({ body: TENANT }),
    "GET /api/me": () => ({ body: ME }),
    "GET /api/drive": () => ({ body: LOCAL }),
    "GET /api/onboarding": () => ({ body: { storage_connected: true, office_details: true, has_project: true } }),
    "GET /api/projects": () => ({ body: [CASA] }),
    ...extra,
  });
}

/** The card's pencil opens its menu (A24, revised 19 Oct 2026). */
async function openMenu() {
  renderAt("/");
  await userEvent.click(await screen.findByRole("button", { name: "Opções do projeto Casa Jardim" }));
  return screen.findByRole("menu");
}

async function openSettings() {
  await userEvent.click(within(await openMenu()).getByRole("menuitem", { name: "Configurações do projeto" }));
  return screen.findByRole("dialog", { name: "Projeto" });
}

beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

describe("the Projeto dialog", () => {
  it("has no photo or archiving: those are in the card's menu", async () => {
    api();
    const dialog = await openSettings();
    expect(within(dialog).queryByRole("button", { name: /Arquivar|capa|foto/i })).toBeNull();
    expect(dialog.querySelector('input[type="file"]')).toBeNull();
  });

  it("closes from its × without saving", async () => {
    const sent = api();
    const dialog = await openSettings();
    await userEvent.click(within(dialog).getByRole("button", { name: "Fechar" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(sent.some((r) => r.method === "PATCH")).toBe(false);
  });

  it("saves the name and client with the version it loaded", async () => {
    const sent = api({ [`PATCH ${PATH}`]: (body: unknown) => ({ body: { ...CASA, ...(body as object), row_version: 5 } }) });
    const dialog = await openSettings();
    const name = within(dialog).getByLabelText(/Nome do projeto/);
    await userEvent.clear(name);
    await userEvent.type(name, "Casa Jardim II");
    await userEvent.click(within(dialog).getByRole("button", { name: "Salvar" }));
    expect(await screen.findByText("Salvo.")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(sent.find((r) => r.method === "PATCH")?.body).toEqual({
      row_version: 4,
      name: "Casa Jardim II",
      client_name: "Família Oliveira",
    });
  });

  it("explains when someone else changed the project meanwhile", async () => {
    api({ [`PATCH ${PATH}`]: () => ({ status: 409, body: { error: "project_changed" } }) });
    const dialog = await openSettings();
    await userEvent.type(within(dialog).getByLabelText(/Nome do projeto/), " II");
    await userEvent.click(within(dialog).getByRole("button", { name: "Salvar" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("alterado por outra pessoa");
    expect(within(dialog).getByLabelText(/Nome do projeto/)).toHaveValue("Casa Jardim II"); // kept
  });

  it("names the project that already has the name", async () => {
    api({
      [`PATCH ${PATH}`]: () => ({ status: 409, body: { error: "project_name_taken", conflict_name: "Casa das Oliveiras" } }),
    });
    const dialog = await openSettings();
    const name = within(dialog).getByLabelText(/Nome do projeto/);
    await userEvent.clear(name);
    await userEvent.type(name, "casa das oliveiras");
    await userEvent.click(within(dialog).getByRole("button", { name: "Salvar" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Já existe o projeto “Casa das Oliveiras”");
  });

  it("changes the client's link, and names the project that has an address", async () => {
    const sent = api({
      [`PATCH ${PATH}`]: (body: unknown) =>
        (body as { slug?: string }).slug === "casa-velha"
          ? { status: 409, body: { error: "slug_taken", conflict_name: "Casa Velha" } }
          : { body: { ...CASA, slug: (body as { slug: string }).slug, row_version: 5 } },
    });
    const dialog = await openSettings();
    const link = within(dialog).getByLabelText(/Link do cliente/);
    await userEvent.clear(link);
    await userEvent.type(link, "Casa-Velha");
    await userEvent.click(within(dialog).getByRole("button", { name: "Salvar" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Este endereço já é do projeto “Casa Velha”");
    await userEvent.clear(link);
    await userEvent.type(link, "casa-jardim-lagoa");
    await userEvent.click(within(dialog).getByRole("button", { name: "Salvar" }));
    expect(await screen.findByText("Salvo.")).toBeInTheDocument();
    expect(sent.filter((r) => r.method === "PATCH").at(-1)?.body).toMatchObject({ slug: "casa-jardim-lagoa" });
  });

  it("protects the page with a password", async () => {
    const sent = api({ [`PATCH ${PATH}`]: () => ({ body: { ...CASA, access_mode: "password", row_version: 5 } }) });
    const dialog = await openSettings();
    await userEvent.click(within(dialog).getByText("Com senha"));
    const password = within(dialog).getByLabelText(/^Senha/);
    await userEvent.type(password, "segredo");
    await userEvent.click(within(dialog).getByRole("button", { name: "Salvar" }));
    expect(await screen.findByText("Salvo.")).toBeInTheDocument();
    expect(sent.find((r) => r.method === "PATCH")?.body).toMatchObject({
      access_mode: "password",
      password: "segredo",
    });
  });

  it("lists the client's emails: added with Enter or Adicionar, removed with ×", async () => {
    const sent = api({ [`PATCH ${PATH}`]: () => ({ body: { ...CASA, row_version: 5 } }) });
    const dialog = await openSettings();
    const field = within(dialog).getByLabelText("Novo e-mail");
    await userEvent.type(field, "Ana@Example.com{Enter}");
    expect(screen.getByRole("dialog", { name: "Projeto" })).toBeInTheDocument(); // Enter added, didn't save
    await userEvent.type(field, "joao@example.com");
    await userEvent.click(within(dialog).getByRole("button", { name: "Adicionar" }));
    await userEvent.type(field, "x@example.com{Enter}");
    await userEvent.click(within(dialog).getByRole("button", { name: "Remover x@example.com" }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Salvar" }));
    expect(await screen.findByText("Salvo.")).toBeInTheDocument();
    expect(sent.find((r) => r.method === "PATCH")?.body).toMatchObject({
      recipients: ["ana@example.com", "joao@example.com"],
    });
  });

  it("saves an email typed but not added", async () => {
    const sent = api({ [`PATCH ${PATH}`]: () => ({ body: { ...CASA, row_version: 5 } }) });
    const dialog = await openSettings();
    await userEvent.type(within(dialog).getByLabelText("Novo e-mail"), "ana@example.com");
    await userEvent.click(within(dialog).getByRole("button", { name: "Salvar" }));
    await screen.findByText("Salvo.");
    expect(sent.find((r) => r.method === "PATCH")?.body).toMatchObject({ recipients: ["ana@example.com"] });
  });

  it("doesn't save while a typed email isn't one, and says which", async () => {
    const sent = api({ [`PATCH ${PATH}`]: () => ({ body: { ...CASA, row_version: 5 } }) });
    const dialog = await openSettings();
    await userEvent.type(within(dialog).getByLabelText("Novo e-mail"), "ana@example.com, joao@example");
    await userEvent.click(within(dialog).getByRole("button", { name: "Salvar" }));
    expect(within(dialog).getByRole("alert")).toHaveTextContent("Este não parece um e-mail: joao@example");
    expect(sent.some((r) => r.method === "PATCH")).toBe(false);
    // The good one was added; fixed, both are saved.
    const field = within(dialog).getByLabelText("Novo e-mail");
    await userEvent.clear(field);
    await userEvent.type(field, "joao@example.com");
    await userEvent.click(within(dialog).getByRole("button", { name: "Salvar" }));
    await screen.findByText("Salvo.");
    expect(sent.find((r) => r.method === "PATCH")?.body).toMatchObject({ recipients: ["ana@example.com", "joao@example.com"] });
  });

  it("shows who unsubscribed, and staff can't remove them to add them back", async () => {
    api({
      "GET /api/projects": () => ({
        body: [{ ...CASA, recipients: [{ email: "ana@example.com", subscribed: false }, { email: "joao@example.com", subscribed: true }] }],
      }),
    });
    const dialog = await openSettings();
    expect(within(dialog).getByText("Cancelou os e-mails")).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "Remover ana@example.com" })).toBeNull();
    expect(within(dialog).getByRole("button", { name: "Remover joao@example.com" })).toBeInTheDocument();
  });

  it("keeps an existing password when its field stays empty", async () => {
    const protectedCasa = { ...CASA, access_mode: "password" as const };
    const sent = api({
      "GET /api/projects": () => ({ body: [protectedCasa] }),
      [`PATCH ${PATH}`]: () => ({ body: { ...protectedCasa, name: "Casa II", row_version: 5 } }),
    });
    const dialog = await openSettings();
    expect(within(dialog).getByText(/Deixe em branco para manter a senha atual/)).toBeInTheDocument();
    const name = within(dialog).getByLabelText(/Nome do projeto/);
    await userEvent.clear(name);
    await userEvent.type(name, "Casa II");
    await userEvent.click(within(dialog).getByRole("button", { name: "Salvar" }));
    expect(await screen.findByText("Salvo.")).toBeInTheDocument();
    const body = sent.find((r) => r.method === "PATCH")?.body as Record<string, unknown>;
    expect(body.password).toBeUndefined();
    expect(body.access_mode).toBeUndefined(); // nothing about access changed
  });

});

describe("the card's menu", () => {
  it("offers the photo, the settings and archiving; Remover foto only with a photo", async () => {
    api({ "GET /api/projects": () => ({ body: [{ ...CASA, cover_url: "/c?v=1" }] }) });
    const items = within(await openMenu()).getAllByRole("menuitem").map((item) => item.textContent);
    expect(items).toEqual(["Trocar foto", "Remover foto", "Configurações do projeto", "Arquivar projeto"]);
  });

  it("offers to add a photo when there is none", async () => {
    api();
    const items = within(await openMenu()).getAllByRole("menuitem").map((item) => item.textContent);
    expect(items).toEqual(["Adicionar foto", "Configurações do projeto", "Arquivar projeto"]);
  });

  it("uploads a chosen photo at once, cropped to 3:2", async () => {
    const sent = api({ [`PUT ${PATH}/cover`]: () => ({ body: { ...CASA, cover_url: "/c?v=2" } }) });
    await userEvent.click(within(await openMenu()).getByRole("menuitem", { name: "Adicionar foto" }));
    await chooseCover();
    expect(await screen.findByText("Foto atualizada.")).toBeInTheDocument();
    const request = sent.find((r) => r.method === "PUT");
    expect(request?.headers.get("Content-Type")).toMatch(/^multipart\/form-data/);
  });

  it("says why a photo failed, with the support code", async () => {
    api({ [`PUT ${PATH}/cover`]: () => ({ status: 503, body: { error: "drive_connect_failed" }, headers: { "X-Request-ID": "abc123" } }) });
    await openMenu();
    await chooseCover();
    expect(await screen.findByText(/Não foi possível conectar o Google Drive.*Código de suporte: abc123/)).toBeInTheDocument();
  });

  it("refuses a file that is not a photo before sending it", async () => {
    const sent = api();
    await openMenu();
    const input = (await screen.findByTestId("project-card")).querySelector('input[type="file"]') as HTMLInputElement;
    await userEvent.upload(input, new File(["%PDF"], "planta.pdf", { type: "application/pdf" }), { applyAccept: false });
    expect(await screen.findByText("Escolha uma imagem JPG, PNG ou WebP.")).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Ajustar a capa" })).toBeNull();
    expect(sent.some((r) => r.method === "PUT")).toBe(false);
  });

  it("removes the photo at once", async () => {
    const sent = api({
      "GET /api/projects": () => ({ body: [{ ...CASA, cover_url: "/c?v=1" }] }),
      [`DELETE ${PATH}/cover`]: () => ({ body: CASA }),
    });
    await userEvent.click(within(await openMenu()).getByRole("menuitem", { name: "Remover foto" }));
    expect(await screen.findByText("Foto removida.")).toBeInTheDocument();
    expect(sent.filter((r) => r.method === "DELETE")).toHaveLength(1);
  });

  it("asks before archiving, and Cancelar leaves the project as it is", async () => {
    const sent = api();
    await userEvent.click(within(await openMenu()).getByRole("menuitem", { name: "Arquivar projeto" }));
    const ask = await screen.findByRole("alertdialog", { name: "Arquivar “Casa Jardim”?" });
    await userEvent.click(within(ask).getByRole("button", { name: "Cancelar" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    expect(sent.some((r) => r.method === "PATCH")).toBe(false);
  });

  it("archives once confirmed, and Desfazer puts it back as it was", async () => {
    const sent = api({
      [`PATCH ${PATH}`]: (body: unknown) => {
        const status = (body as { status: string }).status;
        return { body: { ...CASA, status, row_version: status === "archived" ? 5 : 6 } };
      },
    });
    await userEvent.click(within(await openMenu()).getByRole("menuitem", { name: "Arquivar projeto" }));
    const ask = await screen.findByRole("alertdialog", { name: "Arquivar “Casa Jardim”?" });
    await userEvent.click(within(ask).getByRole("button", { name: "Arquivar" }));
    expect(await screen.findByText("Projeto “Casa Jardim” arquivado.")).toBeInTheDocument();
    expect(screen.queryByRole("alertdialog")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Desfazer" }));
    expect(await screen.findByText("Projeto “Casa Jardim” restaurado.")).toBeInTheDocument();
    const patches = sent.filter((r) => r.method === "PATCH").map((r) => r.body);
    expect(patches).toEqual([
      { row_version: 4, status: "archived" },
      { row_version: 5, status: "active" },
    ]);
  });

  it("a failed Desfazer says why, with the support code", async () => {
    api({
      [`PATCH ${PATH}`]: (body: unknown) =>
        (body as { status: string }).status === "archived"
          ? { body: { ...CASA, status: "archived", row_version: 5 } }
          : { status: 409, body: { error: "project_changed" }, headers: { "X-Request-ID": "abc123" } },
    });
    await userEvent.click(within(await openMenu()).getByRole("menuitem", { name: "Arquivar projeto" }));
    await userEvent.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Arquivar" }));
    await userEvent.click(await screen.findByRole("button", { name: "Desfazer" }));
    expect(await screen.findByText(/alterado por outra pessoa.*Código de suporte: abc123/)).toBeInTheDocument();
  });
});

describe("the card", () => {
  it("marks drafts on the photo, and opens the client's page", async () => {
    api({ "GET /api/projects": () => ({ body: [{ ...CASA, status: "draft" }] }) });
    renderAt("/");
    const card = await screen.findByTestId("project-card");
    expect(within(card).getByText("Rascunho")).toBeInTheDocument();
    expect(within(card).getByRole("heading", { name: "Casa Jardim" })).toBeInTheDocument();
    expect(within(card).getAllByRole("button")).toHaveLength(1); // only the "⋯" (its menu)
    // The card opens the client's page.
    expect(within(card).getByRole("link", { name: "Casa Jardim" })).toHaveAttribute("href", "/casa-jardim");
  });
});

// The card's "Sem e-mail do cliente → Adicionar" (A32): a dialog with only the addresses.
describe("the client's emails dialog", () => {
  async function openEmails() {
    renderAt("/");
    await userEvent.click(await screen.findByRole("button", { name: /Sem e-mail do cliente/ }));
    return screen.findByRole("dialog", { name: "E-mails do cliente" });
  }

  it("saves only the addresses, typed ones included, and the flag goes", async () => {
    let saved = CASA;
    const sent = api({
      "GET /api/projects": () => ({ body: [saved] }),
      [`PATCH ${PATH}`]: () => {
        saved = { ...CASA, row_version: 5, recipients: [{ email: "ana@example.com", subscribed: true }] };
        return { body: saved };
      },
    });
    const dialog = await openEmails();
    await userEvent.type(within(dialog).getByLabelText("Novo e-mail"), "ana@example.com");
    await userEvent.click(within(dialog).getByRole("button", { name: "Salvar" }));
    await screen.findByText("E-mails salvos.");
    expect(sent.find((r) => r.method === "PATCH")?.body).toEqual({ row_version: 4, recipients: ["ana@example.com"] });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "E-mails do cliente" })).toBeNull());
    await waitFor(() => expect(screen.queryByRole("button", { name: /Sem e-mail do cliente/ })).toBeNull());
  });

  it("doesn't save while a typed email isn't one", async () => {
    const sent = api({ [`PATCH ${PATH}`]: () => ({ body: { ...CASA, row_version: 5 } }) });
    const dialog = await openEmails();
    await userEvent.type(within(dialog).getByLabelText("Novo e-mail"), "joao@example");
    await userEvent.click(within(dialog).getByRole("button", { name: "Salvar" }));
    expect(within(dialog).getByRole("alert")).toHaveTextContent("Este não parece um e-mail: joao@example");
    expect(sent.some((r) => r.method === "PATCH")).toBe(false);
  });

  it("keeps an address the client unsubscribed, which staff can't remove", async () => {
    api({
      "GET /api/projects": () => ({ body: [{ ...CASA, recipients: [{ email: "ana@example.com", subscribed: false }] }] }),
    });
    const dialog = await openEmails();
    expect(within(dialog).getByText("Cancelou os e-mails")).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "Remover ana@example.com" })).toBeNull();
  });
});
