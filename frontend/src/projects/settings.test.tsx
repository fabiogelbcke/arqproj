import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fakeApi, ME, renderAt, TENANT } from "../test/render";
import type { ProjectSummary } from "./projects";

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
  current_position: 3,
  current_stage_title: "Estudos Preliminares",
  next_meeting: null,
  created_at: "2026-09-01T12:00:00Z",
  last_activity_at: null,
  row_version: 4,
  cover_url: null,
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

async function openSettings() {
  renderAt("/");
  await userEvent.click(await screen.findByRole("button", { name: "Editar o projeto Casa Jardim" }));
  return screen.findByRole("dialog", { name: "Projeto" });
}

beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

describe("the Projeto dialog", () => {
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

  it("archives, and Desfazer puts it back as it was", async () => {
    const sent = api({
      [`PATCH ${PATH}`]: (body: unknown) => {
        const status = (body as { status: string }).status;
        return { body: { ...CASA, status, row_version: status === "archived" ? 5 : 6 } };
      },
    });
    const dialog = await openSettings();
    await userEvent.click(within(dialog).getByRole("button", { name: "Arquivar" }));
    expect(await screen.findByText("Projeto “Casa Jardim” arquivado.")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Desfazer" }));
    expect(await screen.findByText("Projeto “Casa Jardim” de volta.")).toBeInTheDocument();
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
    const dialog = await openSettings();
    await userEvent.click(within(dialog).getByRole("button", { name: "Arquivar" }));
    await userEvent.click(await screen.findByRole("button", { name: "Desfazer" }));
    expect(await screen.findByText(/alterado por outra pessoa.*Código de suporte: abc123/)).toBeInTheDocument();
  });

  it("removes the cover on Salvar", async () => {
    const withCover = { ...CASA, cover_url: "/api/projects/x/cover?v=1" };
    const sent = api({
      "GET /api/projects": () => ({ body: [withCover] }),
      [`DELETE ${PATH}/cover`]: () => ({ body: CASA }),
    });
    const dialog = await openSettings();
    await userEvent.click(within(dialog).getByRole("button", { name: "Remover capa" }));
    expect(within(dialog).getByText("Sem capa, o painel mostra uma foto de exemplo.")).toBeInTheDocument();
    expect(sent.some((r) => r.method === "DELETE")).toBe(false); // nothing until Salvar
    await userEvent.click(within(dialog).getByRole("button", { name: "Salvar" }));
    expect(await screen.findByText("Salvo.")).toBeInTheDocument();
    expect(sent.filter((r) => r.method === "DELETE")).toHaveLength(1);
    expect(sent.some((r) => r.method === "PATCH")).toBe(false); // name and client unchanged
  });

  it("previews a chosen photo and uploads it on Salvar", async () => {
    const sent = api({ [`PUT ${PATH}/cover`]: () => ({ body: { ...CASA, cover_url: "/c?v=2" } }) });
    const dialog = await openSettings();
    const input = dialog.querySelector('input[type="file"]') as HTMLInputElement;
    await userEvent.upload(input, new File(["jpg"], "obra.jpg", { type: "image/jpeg" }));
    expect(within(dialog).getByRole("img", { name: "Prévia da nova capa" })).toBeInTheDocument();
    expect(sent.some((r) => r.method === "PUT")).toBe(false);
    await userEvent.click(within(dialog).getByRole("button", { name: "Salvar" }));
    expect(await screen.findByText("Salvo.")).toBeInTheDocument();
    const request = sent.find((r) => r.method === "PUT");
    expect(request?.headers.get("Content-Type")).toMatch(/^multipart\/form-data/);
  });

  it("refuses a file that is not a photo before sending it", async () => {
    api();
    const dialog = await openSettings();
    const input = dialog.querySelector('input[type="file"]') as HTMLInputElement;
    await userEvent.upload(input, new File(["%PDF"], "planta.pdf", { type: "application/pdf" }), {
      applyAccept: false,
    });
    expect(within(dialog).getByRole("alert")).toHaveTextContent("Escolha uma imagem JPG, PNG ou WebP.");
    expect(within(dialog).getByRole("button", { name: "Salvar" })).toBeDisabled();
  });

  it("after a failed photo, a retry doesn't resend the name it already saved", async () => {
    let puts = 0;
    const sent = api({
      [`PATCH ${PATH}`]: (body: unknown) => ({ body: { ...CASA, ...(body as object), row_version: 5 } }),
      [`PUT ${PATH}/cover`]: () =>
        ++puts === 1 ? { status: 503, body: { error: "drive_connect_failed" } } : { body: CASA },
    });
    const dialog = await openSettings();
    const name = within(dialog).getByLabelText(/Nome do projeto/);
    await userEvent.clear(name);
    await userEvent.type(name, "Casa Nova");
    const input = dialog.querySelector('input[type="file"]') as HTMLInputElement;
    await userEvent.upload(input, new File(["jpg"], "obra.jpg", { type: "image/jpeg" }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Salvar" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Não foi possível conectar o Google Drive");
    await userEvent.click(within(dialog).getByRole("button", { name: "Salvar" }));
    expect(await screen.findByText("Salvo.")).toBeInTheDocument();
    expect(sent.filter((r) => r.method === "PATCH")).toHaveLength(1);
    expect(sent.filter((r) => r.method === "PUT")).toHaveLength(2);
  });
});

describe("the card", () => {
  it("marks drafts on the photo, and the title opens nothing", async () => {
    api({ "GET /api/projects": () => ({ body: [{ ...CASA, status: "draft" }] }) });
    renderAt("/");
    const card = await screen.findByTestId("project-card");
    expect(within(card).getByText("Rascunho")).toBeInTheDocument();
    expect(within(card).getByRole("heading", { name: "Casa Jardim" })).toBeInTheDocument();
    expect(within(card).getAllByRole("button")).toHaveLength(1); // only the pencil
  });
});
