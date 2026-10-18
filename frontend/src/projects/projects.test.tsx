import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fakeApi, ME, renderAt, TENANT } from "../test/render";
import {
  compareProjects,
  coverIndex,
  loadSort,
  matches,
  saveSort,
  suggestedSlug,
  type ProjectSummary,
} from "./projects";

const LOCAL = { kind: "folder", writer_status: "none", reader_status: "unknown", account_email: null, folder_url: null, can_manage: true };
const NONE = { ...LOCAL, kind: null };
const OPTIONS = {
  types: [
    { key: "architecture", label: "Projeto Arquitetônico", stages: ["briefing", "survey", "permit_documents"] },
    { key: "interiors", label: "Projeto de Interiores", stages: ["briefing", "survey", "detailing"] },
  ],
  stages: [
    { key: "briefing", title: "Briefing" },
    { key: "survey", title: "Levantamento" },
    { key: "permit_documents", title: "Projeto Legal" },
    { key: "detailing", title: "Detalhamentos" },
  ],
};

function project(changes: Partial<ProjectSummary>): ProjectSummary {
  return {
    id: "00000000-0000-0000-0000-000000000001",
    name: "Casa Jardim",
    client_name: "Família Oliveira",
    slug: "casa-jardim",
    status: "active",
    project_type: "architecture",
    project_type_label: "Projeto Arquitetônico",
    stage_count: 7,
    recipients: [],
    current_position: 3,
    current_stage_title: "Estudos Preliminares",
    next_meeting: null,
    created_at: "2026-09-01T12:00:00Z",
    last_activity_at: null,
    row_version: 1,
    cover_url: null,
    access_mode: "public",
    ...changes,
  };
}

const LIST = [
  project({}),
  project({ id: "2", name: "Conceição", client_name: "Ana", slug: "conceicao", status: "active", created_at: "2026-10-01T12:00:00Z" }),
  project({ id: "3", name: "Refúgio", client_name: "Helena", slug: "refugio", status: "completed" }),
  project({
    id: "4",
    name: "Apartamento",
    client_name: "Clara",
    slug: "apto",
    next_meeting: { title: "Apresentação", starts_at: "2026-10-21T19:00:00Z" },
  }),
];

function api(drive: object = LOCAL, extra = {}) {
  return fakeApi({
    "GET /api/tenant": () => ({ body: TENANT }),
    "GET /api/me": () => ({ body: ME }),
    "GET /api/drive": () => ({ body: drive }),
    "GET /api/onboarding": () => ({ body: { storage_connected: true, office_details: true, has_project: true } }),
    "GET /api/projects": () => ({ body: LIST }),
    "GET /api/project-types": () => ({ body: OPTIONS }),
    ...extra,
  });
}

beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

describe("the project list", () => {
  it("groups projects, with completed ones folded away", async () => {
    api();
    renderAt("/");
    const active = await screen.findByRole("region", { name: "Em andamento" });
    expect(within(active).getAllByTestId("project-card")).toHaveLength(3);
    expect(within(active).getByLabelText("3 projetos em andamento de 4 exibidos")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Rascunhos" })).toBeNull(); // no drafts (A35)

    const fold = screen.getByRole("button", { name: "Concluídos" });
    expect(screen.queryByText("Refúgio")).not.toBeVisible();
    await userEvent.click(fold);
    expect(screen.getByText("Refúgio")).toBeVisible();
    expect(screen.getByText("Projeto concluído")).toBeInTheDocument();
  });

  it("on a phone, shows one group at a time from two tabs", async () => {
    api();
    renderAt("/");
    const tabs = await screen.findByRole("group", { name: "Grupos de projetos" });
    const activeTab = within(tabs).getByRole("button", { name: "Em andamento 3" });
    const completedTab = within(tabs).getByRole("button", { name: "Concluídos 1" });
    expect(activeTab).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(completedTab);
    expect(completedTab).toHaveAttribute("aria-pressed", "true");
    expect(activeTab).toHaveAttribute("aria-pressed", "false");
    // Which group shows is the stylesheet's job on phones; the choice is on the wrapper.
    expect(document.querySelector("[data-phone-group]")).toHaveAttribute("data-phone-group", "completed");
  });

  it("on a phone, a tab with no projects has no count, and says so when chosen", async () => {
    api(LOCAL, { "GET /api/projects": () => ({ body: LIST.filter((p) => p.status !== "completed") }) });
    renderAt("/");
    const tabs = await screen.findByRole("group", { name: "Grupos de projetos" });
    const completedTab = within(tabs).getByRole("button", { name: "Concluídos" }); // no "0"
    await userEvent.click(completedTab);
    expect(screen.getByText("Nenhum projeto concluído.")).toBeInTheDocument();
  });

  it("shows meeting times in the office's time zone", async () => {
    api();
    renderAt("/");
    expect(await screen.findByText("21/10/2026, 16:00")).toBeInTheDocument(); // 19:00 UTC
  });

  it("finds projects by name or client, ignoring accents and case", async () => {
    api();
    renderAt("/");
    const search = await screen.findByRole("searchbox", { name: "Buscar projetos" });
    await userEvent.type(search, "conceicao");
    expect(screen.getAllByTestId("project-card")).toHaveLength(1);
    await userEvent.clear(search);
    await userEvent.type(search, "OLIVEIRA");
    expect(screen.getAllByTestId("project-card")).toHaveLength(1);
    await userEvent.clear(search);
    await userEvent.type(search, "xyz");
    expect(screen.getByText("Nenhum projeto encontrado para “xyz”.")).toBeInTheDocument();
  });

  it("remembers the chosen order on this device", async () => {
    api();
    renderAt("/");
    await userEvent.selectOptions(await screen.findByLabelText("Ordenar por"), "name");
    expect(loadSort()).toEqual({ key: "name", direction: "asc" });
    const active = screen.getByRole("region", { name: "Em andamento" });
    const names = within(active).getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(names).toEqual(["Apartamento", "Casa Jardim", "Conceição"]);
  });

  it("an office with no projects is invited to create one", async () => {
    api(LOCAL, { "GET /api/projects": () => ({ body: [] }) });
    renderAt("/");
    expect(await screen.findByText("Crie o primeiro projeto para começar.")).toBeInTheDocument();
  });
});

describe("Novo projeto", () => {
  it("closes from its × without creating anything", async () => {
    const sent = api();
    renderAt("/");
    await userEvent.click(await screen.findByRole("button", { name: "Novo projeto" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Fechar" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(sent.some((r) => r.method === "POST")).toBe(false);
  });

  it("sends the project with an address from its name and a one-time key", async () => {
    const sent = api(LOCAL, {
      "POST /api/projects": (body: unknown) => ({
        status: 201,
        body: project({ id: "9", name: (body as { name: string }).name, status: "active" }),
      }),
    });
    renderAt("/");
    await userEvent.click(await screen.findByRole("button", { name: "Novo projeto" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(/Nome do projeto/), "Casa do Lago — Conceição");
    await userEvent.type(within(dialog).getByLabelText(/Cliente/), "Família Souza");
    expect(within(dialog).getByLabelText(/Endereço da página/)).toHaveValue("casa-do-lago-conceicao");
    await userEvent.click(within(dialog).getByText("Projeto de Interiores"));
    // The type's usual stages come ticked; any can be ticked or unticked.
    expect(within(dialog).getByRole("checkbox", { name: "Detalhamentos" })).toBeChecked();
    expect(within(dialog).getByRole("checkbox", { name: "Projeto Legal" })).not.toBeChecked();
    await userEvent.click(within(dialog).getByText("Levantamento"));
    await userEvent.click(within(dialog).getByText("Projeto Legal"));
    await userEvent.click(within(dialog).getByRole("button", { name: "Criar projeto" }));

    expect(await screen.findByText("Projeto “Casa do Lago — Conceição” criado.")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    const request = sent.find((r) => r.method === "POST");
    expect(request?.body).toMatchObject({
      name: "Casa do Lago — Conceição",
      client_name: "Família Souza",
      project_type: "interiors",
      slug: "casa-do-lago-conceicao",
    });
    expect(new Set((request?.body as { stages: string[] }).stages)).toEqual(
      new Set(["briefing", "detailing", "permit_documents"]),
    );
    expect((request?.body as { creation_key: string }).creation_key.length).toBeGreaterThanOrEqual(16);
    expect(request?.headers.get("X-CSRF-Token")).toBe("csrf-123");
  });

  it("if the types fail to load, offers to try again and blocks creating", async () => {
    let fail = true;
    api(LOCAL, {
      "GET /api/project-types": () => (fail ? { status: 503, body: { error: "unexpected" } } : { body: OPTIONS }),
    });
    renderAt("/");
    await userEvent.click(await screen.findByRole("button", { name: "Novo projeto" }));
    const dialog = await screen.findByRole("dialog");
    const retry = await within(dialog).findByRole("button", { name: "Tentar de novo" });
    expect(within(dialog).getByRole("button", { name: "Criar projeto" })).toBeDisabled();
    fail = false;
    await userEvent.click(retry);
    expect(await within(dialog).findByRole("checkbox", { name: "Briefing" })).toBeChecked();
    expect(within(dialog).getByRole("button", { name: "Criar projeto" })).toBeEnabled();
  });

  it("changing the type ticks its usual stages again", async () => {
    api();
    renderAt("/");
    await userEvent.click(await screen.findByRole("button", { name: "Novo projeto" }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByRole("checkbox", { name: "Projeto Legal" })).toBeChecked();
    await userEvent.click(within(dialog).getByText("Briefing")); // untick
    await userEvent.click(within(dialog).getByText("Projeto de Interiores"));
    expect(within(dialog).getByRole("checkbox", { name: "Briefing" })).toBeChecked();
    expect(within(dialog).getByRole("checkbox", { name: "Projeto Legal" })).not.toBeChecked();
    expect(within(dialog).getByText(/3 etapas marcadas/)).toBeInTheDocument();
  });

  it("a retry after a failure reuses the same key, so it never makes two", async () => {
    let calls = 0;
    const sent = api(LOCAL, {
      "POST /api/projects": () =>
        ++calls === 1 ? { status: 503, body: { error: "drive_connect_failed" } } : { status: 201, body: project({}) },
    });
    renderAt("/");
    await userEvent.click(await screen.findByRole("button", { name: "Novo projeto" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(/Nome do projeto/), "Casa");
    await userEvent.type(within(dialog).getByLabelText(/Cliente/), "Ana");
    await userEvent.click(within(dialog).getByRole("button", { name: "Criar projeto" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Não foi possível conectar o Google Drive");
    await userEvent.click(within(dialog).getByRole("button", { name: "Criar projeto" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    const keys = sent.filter((r) => r.method === "POST").map((r) => (r.body as { creation_key: string }).creation_key);
    expect(keys).toHaveLength(2);
    expect(keys[0]).toBe(keys[1]);
  });

  it("names the project that already has the address", async () => {
    api(LOCAL, {
      "POST /api/projects": () => ({ status: 409, body: { error: "slug_taken", conflict_name: "Casa Jardim" } }),
    });
    renderAt("/");
    await userEvent.click(await screen.findByRole("button", { name: "Novo projeto" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(/Nome do projeto/), "Casa Jardim");
    await userEvent.type(within(dialog).getByLabelText(/Cliente/), "Ana");
    await userEvent.click(within(dialog).getByRole("button", { name: "Criar projeto" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "Este endereço já é do projeto “Casa Jardim”. Escolha outro.",
    );
  });

  it("names the project that already has the name", async () => {
    api(LOCAL, {
      "POST /api/projects": () => ({ status: 409, body: { error: "project_name_taken", conflict_name: "Casa Jardim" } }),
    });
    renderAt("/");
    await userEvent.click(await screen.findByRole("button", { name: "Novo projeto" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(/Nome do projeto/), "casa jardim");
    await userEvent.type(within(dialog).getByLabelText(/Cliente/), "Ana");
    await userEvent.click(within(dialog).getByRole("button", { name: "Criar projeto" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Já existe o projeto “Casa Jardim”.");
  });

  it("without Google Drive, the owner connects it from the dialog, straight to Google", async () => {
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });
    const sent = api(NONE, { "POST /api/drive/connect": () => ({ body: { url: "https://accounts.google.example/consent" } }) });
    renderAt("/");
    await userEvent.click(await screen.findByRole("button", { name: "Novo projeto" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Para criar projetos, conecte o Google Drive do escritório.")).toBeInTheDocument();
    expect(within(dialog).queryByLabelText(/Nome do projeto/)).not.toBeInTheDocument();
    expect(within(dialog).queryByRole("link")).toBeNull(); // no detour through Configurações
    await userEvent.click(within(dialog).getByRole("button", { name: "Conectar Google Drive" }));
    await waitFor(() => expect(assign).toHaveBeenCalledWith("https://accounts.google.example/consent"));
    expect(sent.some((r) => r.method === "POST" && r.path === "/api/drive/connect")).toBe(true);
  });

  it("without Google Drive, a member is told who can connect it", async () => {
    fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/me": () => ({ body: { ...ME, role: "member" } }),
      "GET /api/drive": () => ({ body: NONE }),
      "GET /api/onboarding": () => ({ body: { storage_connected: false, office_details: true, has_project: true } }),
      "GET /api/projects": () => ({ body: LIST }),
      "GET /api/project-types": () => ({ body: OPTIONS }),
    });
    renderAt("/");
    await userEvent.click(await screen.findByRole("button", { name: "Novo projeto" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/Peça ao responsável pelo escritório/)).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "Conectar Google Drive" })).toBeNull();
  });
});

describe("helpers", () => {
  it("suggests a plain lowercase address", () => {
    expect(suggestedSlug("  Casa Jardim — Lagoa da Conceição! ")).toBe("casa-jardim-lagoa-da-conceicao");
    expect(suggestedSlug("—")).toBe("");
  });

  it("matches every word of the search, in any order", () => {
    expect(matches(project({}), "oliveira casa")).toBe(true);
    expect(matches(project({}), "oliveira lago")).toBe(false);
  });

  it("orders by last update, falling back to creation", () => {
    const old = project({ id: "a", name: "A", created_at: "2026-01-01T00:00:00Z" });
    const touched = project({ id: "b", name: "B", created_at: "2025-01-01T00:00:00Z", last_activity_at: "2026-06-01T00:00:00Z" });
    const sorted = [old, touched].sort(compareProjects({ key: "updated", direction: "desc" }, "pt-BR"));
    expect(sorted.map((p) => p.name)).toEqual(["B", "A"]);
  });

  it("ignores a broken or unknown saved order", () => {
    localStorage.setItem("painel.projectSort", "{not json");
    expect(loadSort()).toEqual({ key: "updated", direction: "desc" });
    localStorage.setItem("painel.projectSort", JSON.stringify({ key: "colour", direction: "asc" }));
    expect(loadSort()).toEqual({ key: "updated", direction: "desc" });
    saveSort({ key: "client", direction: "desc" });
    expect(loadSort()).toEqual({ key: "client", direction: "desc" });
  });

  it("gives a project the same placeholder photo every time", () => {
    expect(coverIndex("abc", 10)).toBe(coverIndex("abc", 10));
    expect(coverIndex("abc", 10)).toBeLessThan(10);
  });
});
