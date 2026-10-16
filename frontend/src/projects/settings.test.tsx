import { screen, waitFor, within } from "@testing-library/react";
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
  await userEvent.click(await screen.findByRole("button", { name: "Abrir as configurações de Casa Jardim" }));
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
    await userEvent.click(within(dialog).getByRole("button", { name: "Salvar" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("alterado por outra pessoa");
    expect(within(dialog).getByLabelText(/Nome do projeto/)).toHaveValue("Casa Jardim"); // kept
  });

  it("names the project that already has the name", async () => {
    api({
      [`PATCH ${PATH}`]: () => ({ status: 409, body: { error: "project_name_taken", conflict_name: "Casa das Oliveiras" } }),
    });
    const dialog = await openSettings();
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

  it("removes the cover", async () => {
    const withCover = { ...CASA, cover_url: "/api/projects/x/cover?v=1" };
    api({
      "GET /api/projects": () => ({ body: [withCover] }),
      [`DELETE ${PATH}/cover`]: () => ({ body: CASA }),
    });
    const dialog = await openSettings();
    await userEvent.click(within(dialog).getByRole("button", { name: "Remover capa" }));
    expect(await screen.findByText(/Capa removida/)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Definir capa" })).toBeInTheDocument();
  });
});

describe("the card's photo button", () => {
  async function openCover() {
    renderAt("/");
    await userEvent.click(await screen.findByRole("button", { name: "Trocar foto de Casa Jardim" }));
    return screen.findByRole("dialog", { name: "Trocar foto" });
  }

  it("previews the chosen photo, then saves it", async () => {
    const sent = api({ [`PUT ${PATH}/cover`]: () => ({ body: { ...CASA, cover_url: "/c?v=2" } }) });
    const dialog = await openCover();
    const save = within(dialog).getByRole("button", { name: "Salvar foto" });
    expect(save).toBeDisabled();
    const input = dialog.querySelector('input[type="file"]') as HTMLInputElement;
    await userEvent.upload(input, new File(["jpg"], "obra.jpg", { type: "image/jpeg" }));
    expect(within(dialog).getByRole("img", { name: "Prévia da nova capa" })).toBeInTheDocument();
    await userEvent.click(save);
    expect(await screen.findByText("Foto da capa atualizada.")).toBeInTheDocument();
    const request = sent.find((r) => r.method === "PUT");
    expect(request?.headers.get("Content-Type")).toMatch(/^multipart\/form-data/);
  });

  it("refuses a file that is not a photo before sending it", async () => {
    const sent = api();
    const dialog = await openCover();
    const input = dialog.querySelector('input[type="file"]') as HTMLInputElement;
    await userEvent.upload(input, new File(["%PDF"], "planta.pdf", { type: "application/pdf" }), {
      applyAccept: false,
    });
    expect(within(dialog).getByRole("alert")).toHaveTextContent("Escolha uma imagem JPG, PNG ou WebP.");
    expect(within(dialog).getByRole("button", { name: "Salvar foto" })).toBeDisabled();
    await waitFor(() => expect(sent.some((r) => r.method === "PUT")).toBe(false));
  });
});
