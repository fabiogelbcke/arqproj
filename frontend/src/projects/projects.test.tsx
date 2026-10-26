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
    completed_stage_count: 2,
    current_position: null, // the previous release's (A30), unread now
    current_stage_title: null,
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
  project({ id: "3", name: "Refúgio", client_name: "Helena", slug: "refugio", status: "completed", completed_stage_count: 7 }),
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
  it("groups projects: in progress, then completed, both open", async () => {
    api();
    renderAt("/");
    const active = await screen.findByRole("region", { name: "Em andamento" });
    expect(within(active).getAllByTestId("project-card")).toHaveLength(3);
    expect(within(active).getByText("3")).toBeInTheDocument(); // how many, beside the heading
    expect(screen.queryByRole("region", { name: "Rascunhos" })).toBeNull(); // no drafts (A35)

    const completed = screen.getByRole("region", { name: "Concluídos" });
    expect(within(completed).getByText("Refúgio")).toBeVisible();
    expect(within(completed).getByText("7 de 7 etapas concluídas")).toBeInTheDocument();
  });

  it("shows on each card how many stages are completed, in words and as a bar", async () => {
    api(LOCAL, {
      "GET /api/projects": () => ({
        body: [project({}), project({ id: "5", name: "Sem etapas", slug: "vazio", stage_count: 0, completed_stage_count: 0 })],
      }),
    });
    renderAt("/");
    const [casa, empty] = await screen.findAllByTestId("project-card");
    expect(within(casa!).getByText("2 de 7 etapas concluídas")).toBeInTheDocument();
    expect(within(casa!).getByRole("progressbar")).toHaveAttribute("aria-valuenow", "2");
    expect(within(empty!).queryByRole("progressbar")).toBeNull(); // nothing to fill
  });

  it("filters by project type with a chip for each type in use", async () => {
    api(LOCAL, {
      "GET /api/projects": () => ({
        body: [
          ...LIST,
          project({ id: "5", name: "Loft", slug: "loft", project_type: "interiors", project_type_label: "Projeto de Interiores" }),
        ],
      }),
    });
    renderAt("/");
    const chips = await screen.findByRole("radiogroup", { name: "Tipos de projeto" });
    // "Todos", then the types in use only, by their short names, alphabetically
    // (no Paisagismo here).
    expect(within(chips).getAllByRole("radio").map((chip) => chip.textContent)).toEqual([
      "Todos",
      "Arquitetônico",
      "Interiores",
    ]);
    expect(within(chips).getByRole("radio", { name: "Todos" })).toBeChecked();
    await userEvent.click(within(chips).getByRole("radio", { name: "Interiores" }));
    expect(screen.getAllByTestId("project-card").map((card) => within(card).getByRole("heading").textContent)).toEqual([
      "Loft",
    ]);
    // With a search too: both apply, and an empty result says it's the type.
    await userEvent.type(screen.getByRole("searchbox", { name: "Buscar projetos" }), "jardim");
    expect(screen.getByText("Nenhum projeto encontrado para “jardim”.")).toBeInTheDocument();
    await userEvent.click(within(chips).getByRole("radio", { name: "Todos" }));
    expect(screen.getAllByTestId("project-card")).toHaveLength(1);
  });

  it("names a type without a short name by its full name", async () => {
    const own = project({ id: "6", name: "Galpão", slug: "galpao", project_type: "warehouses", project_type_label: "Galpões Industriais" });
    api(LOCAL, { "GET /api/projects": () => ({ body: [...LIST, own] }) });
    renderAt("/");
    const chips = await screen.findByRole("radiogroup", { name: "Tipos de projeto" });
    expect(within(chips).getByRole("radio", { name: "Galpões Industriais" })).toBeInTheDocument();
  });

  it("shows no type chips when every project is of one type", async () => {
    api();
    renderAt("/");
    await screen.findByRole("region", { name: "Em andamento" });
    expect(screen.queryByRole("radiogroup", { name: "Tipos de projeto" })).toBeNull();
  });

  it("goes back to every project when the chosen type's last project is archived", async () => {
    const loft = project({ id: "5", name: "Loft", slug: "loft", project_type: "interiors", project_type_label: "Projeto de Interiores" });
    let list = [...LIST, loft];
    api(LOCAL, {
      "GET /api/projects": () => ({ body: list }),
      [`PATCH /api/projects/${loft.id}`]: () => {
        list = LIST;
        return { body: { ...loft, status: "archived", row_version: 2 } };
      },
    });
    renderAt("/");
    const chips = await screen.findByRole("radiogroup", { name: "Tipos de projeto" });
    await userEvent.click(within(chips).getByRole("radio", { name: "Interiores" }));
    expect(screen.getAllByTestId("project-card")).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: "Opções do projeto Loft" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Arquivar projeto" }));
    await userEvent.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Arquivar" }));
    // One type left: no chips, and every project, not an empty list.
    await waitFor(() => expect(screen.queryByRole("radiogroup", { name: "Tipos de projeto" })).toBeNull());
    expect(screen.getAllByTestId("project-card")).toHaveLength(4);
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

  it("sorts by an order and its direction, chosen together, and remembers it on this device", async () => {
    api();
    renderAt("/");
    const select = await screen.findByLabelText("Ordenar por");
    // Each order in both directions, dates newest first; no separate direction button.
    expect(within(select).getAllByRole("option").map((option) => option.textContent)).toEqual([
      "Atualização: mais recentes",
      "Atualização: mais antigas",
      "Criação: mais recentes",
      "Criação: mais antigas",
      "Nome: A–Z",
      "Nome: Z–A",
      "Cliente: A–Z",
      "Cliente: Z–A",
      "Tipo: A–Z",
      "Tipo: Z–A",
    ]);
    expect(screen.queryByRole("button", { name: /Ordem (de)?crescente/ })).toBeNull();
    const names = () =>
      within(screen.getByRole("region", { name: "Em andamento" }))
        .getAllByRole("heading", { level: 3 })
        .map((h) => h.textContent);
    await userEvent.selectOptions(select, "Nome: A–Z");
    expect(loadSort()).toEqual({ key: "name", direction: "asc" });
    expect(names()).toEqual(["Apartamento", "Casa Jardim", "Conceição"]);
    await userEvent.selectOptions(select, "Nome: Z–A");
    expect(loadSort()).toEqual({ key: "name", direction: "desc" });
    expect(names()).toEqual(["Conceição", "Casa Jardim", "Apartamento"]);
  });

  it("shows the first 8 completed projects, and the rest on \"Ver todos\"", async () => {
    const done = Array.from({ length: 10 }, (_, i) =>
      project({ id: `c${i}`, name: `Concluído ${i + 1}`, slug: `c${i}`, status: "completed" }),
    );
    api(LOCAL, { "GET /api/projects": () => ({ body: [...LIST, ...done] }) });
    saveSort({ key: "name", direction: "asc" });
    renderAt("/");
    const completed = await screen.findByRole("region", { name: "Concluídos" });
    expect(within(completed).getAllByTestId("project-card")).toHaveLength(8);
    expect(within(completed).getByText("11")).toBeInTheDocument(); // the bar counts them all
    const more = within(completed).getByRole("button", { name: "Ver todos (11)" });
    expect(more).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(more);
    expect(within(completed).getAllByTestId("project-card")).toHaveLength(11);
    await userEvent.click(within(completed).getByRole("button", { name: "Ver menos" }));
    expect(within(completed).getAllByTestId("project-card")).toHaveLength(8);
    // While searching, every match shows.
    await userEvent.type(screen.getByRole("searchbox", { name: "Buscar projetos" }), "concluído");
    expect(within(screen.getByRole("region", { name: "Concluídos" })).getAllByTestId("project-card")).toHaveLength(10);
    expect(screen.queryByRole("button", { name: /Ver todos/ })).toBeNull();
  });

  it("keeps the search and the type in the address, and starts from them", async () => {
    const loft = project({ id: "5", name: "Loft", slug: "loft", project_type: "interiors", project_type_label: "Projeto de Interiores" });
    api(LOCAL, { "GET /api/projects": () => ({ body: [...LIST, loft] }) });
    const router = renderAt("/?type=interiors");
    const chips = await screen.findByRole("radiogroup", { name: "Tipos de projeto" });
    expect(within(chips).getByRole("radio", { name: "Interiores" })).toBeChecked();
    expect(screen.getAllByTestId("project-card")).toHaveLength(1);
    await userEvent.click(within(chips).getByRole("radio", { name: "Todos" }));
    expect(router.state.location.search).toBe(""); // the default isn't written
    await userEvent.type(screen.getByRole("searchbox", { name: "Buscar projetos" }), "casa");
    expect(new URLSearchParams(router.state.location.search).get("q")).toBe("casa");
    // Typing replaced the address rather than adding a step per letter.
    expect(router.state.historyAction).toBe("REPLACE");
  });

  it("tells screen readers how many projects a search or a type leaves", async () => {
    api();
    renderAt("/");
    const search = await screen.findByRole("searchbox", { name: "Buscar projetos" });
    const status = screen.getByText("", { selector: "p[role=status]" });
    expect(status).toBeEmptyDOMElement(); // nothing to say before a search
    await userEvent.type(search, "casa");
    expect(status).toHaveTextContent("1 projeto encontrado");
    await userEvent.clear(search);
    await userEvent.type(search, "a");
    expect(status).toHaveTextContent("4 projetos encontrados");
    await userEvent.type(search, "xyz");
    expect(status).toHaveTextContent("Nenhum projeto encontrado");
  });

  it("shows faded cards while the projects load", async () => {
    api(LOCAL, { "GET /api/projects": () => new Promise(() => {}) });
    renderAt("/");
    await waitFor(() => expect(document.querySelector("[aria-busy=true]")).not.toBeNull());
    expect(screen.getByText("Carregando…")).toBeInTheDocument(); // for screen readers
    expect(screen.queryByTestId("project-card")).toBeNull();
  });

  it("a search with no results offers to clear it, and goes back to the box", async () => {
    api();
    renderAt("/");
    const search = await screen.findByRole("searchbox", { name: "Buscar projetos" });
    await userEvent.type(search, "xyz");
    await userEvent.click(screen.getByRole("button", { name: "Limpar busca" }));
    expect(search).toHaveValue("");
    expect(search).toHaveFocus();
    expect(screen.getAllByTestId("project-card")).toHaveLength(4);
  });

  it("an office with no projects is invited to create one, without the list's tools", async () => {
    api(LOCAL, { "GET /api/projects": () => ({ body: [] }) });
    renderAt("/");
    const empty = await screen.findByRole("region", { name: "Seus projetos aparecem aqui" });
    // Nothing to search, sort, filter or switch between yet.
    expect(screen.queryByRole("searchbox")).toBeNull();
    expect(screen.queryByLabelText("Ordenar por")).toBeNull();
    expect(screen.queryByRole("radiogroup", { name: "Tipos de projeto" })).toBeNull();
    expect(screen.queryByRole("group", { name: "Grupos de projetos" })).toBeNull();
    // The way to start is in the empty state itself.
    await userEvent.click(within(empty).getByRole("button", { name: "Novo projeto" }));
    expect(await screen.findByRole("dialog", { name: "Novo projeto" })).toBeInTheDocument();
  });

  it("an office with projects gets the tools and the tabs, not the empty state", async () => {
    api();
    renderAt("/");
    await screen.findByRole("group", { name: "Grupos de projetos" });
    expect(screen.getByRole("searchbox", { name: "Buscar projetos" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Seus projetos aparecem aqui" })).toBeNull();
  });
});

describe("with Google Drive disconnected", () => {
  const GOOGLE = { kind: "google", reader_status: "ok", account_email: "ana@alinea.example", folder_url: null, can_manage: true, has_folder: true };
  const DISCONNECTED = { ...GOOGLE, writer_status: "none" };

  it("hides the projects, the search and Novo projeto, and offers to reconnect", async () => {
    api(DISCONNECTED);
    renderAt("/");
    const state = await screen.findByRole("region", { name: "Google Drive desconectado" });
    expect(within(state).getByText(/Os arquivos continuam na pasta do Drive/)).toBeVisible();
    await userEvent.click(within(state).getByRole("button", { name: "Reconectar" }));
    expect(await screen.findByRole("heading", { name: "Armazenamento" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("link", { name: "Projetos" }));
    await screen.findByRole("region", { name: "Google Drive desconectado" });
    expect(screen.queryAllByTestId("project-card")).toHaveLength(0);
    expect(screen.queryByRole("searchbox")).toBeNull();
    expect(screen.queryByRole("button", { name: "Novo projeto" })).toBeNull();
    expect(screen.queryByText("Casa Jardim")).toBeNull();
  });

  it("tells a member the owner reconnects", async () => {
    api({ ...DISCONNECTED, can_manage: false });
    renderAt("/");
    const state = await screen.findByRole("region", { name: "Google Drive desconectado" });
    expect(within(state).getByText(/até que o responsável pelo escritório reconecte/)).toBeVisible();
    expect(screen.queryByRole("button", { name: "Reconectar" })).toBeNull();
    expect(screen.queryAllByTestId("project-card")).toHaveLength(0);
  });

  // Only a deliberate disconnect hides them: an expired grant keeps the client
  // pages working, and a never-connected office has its first steps.
  it.each([
    ["expired", { ...GOOGLE, writer_status: "expired" }],
    ["connected", { ...GOOGLE, writer_status: "connected" }],
    ["never connected", { ...NONE, has_folder: false }],
  ])("shows the projects when Drive is %s", async (_, drive) => {
    api(drive);
    renderAt("/");
    const active = await screen.findByRole("region", { name: "Em andamento" });
    expect(within(active).getAllByTestId("project-card")).toHaveLength(3);
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

  it("sends the client's emails with the project, a typed one too, and stops for one that isn't an email", async () => {
    const sent = api(LOCAL, {
      "POST /api/projects": () => ({ status: 201, body: project({ id: "9", name: "Casa do Lago" }) }),
    });
    renderAt("/");
    await userEvent.click(await screen.findByRole("button", { name: "Novo projeto" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(/Nome do projeto/), "Casa do Lago");
    await userEvent.type(within(dialog).getByLabelText(/Cliente/), "Família Souza");
    const emails = within(dialog).getByLabelText("Novo e-mail");
    await userEvent.type(emails, "ana@souza.com.br{Enter}joao@souza");
    await userEvent.click(within(dialog).getByRole("button", { name: "Criar projeto" }));
    expect(within(dialog).getByRole("alert")).toHaveTextContent("Este não parece um e-mail: joao@souza");
    expect(sent.some((r) => r.method === "POST")).toBe(false);
    await userEvent.type(emails, ".com.br");
    await userEvent.click(within(dialog).getByRole("button", { name: "Criar projeto" }));
    await screen.findByText("Projeto “Casa do Lago” criado.");
    expect(sent.find((r) => r.method === "POST")?.body).toMatchObject({
      recipients: ["ana@souza.com.br", "joao@souza.com.br"],
    });
  });

  it("flags an active project nobody gets updates for, and its flag opens where to add them", async () => {
    api(LOCAL, {
      "GET /api/projects": () => ({
        body: [
          project({}), // no address
          project({ id: "2", name: "Conceição", slug: "conceicao", recipients: [{ email: "ana@x.com", subscribed: true }] }),
          project({ id: "3", name: "Refúgio", slug: "refugio", recipients: [{ email: "ana@x.com", subscribed: false }] }),
          project({ id: "4", name: "Pronto", slug: "pronto", status: "completed" }),
        ],
      }),
    });
    renderAt("/");
    const card = async (name: string) => (await screen.findByRole("link", { name })).closest("li")!;
    expect(within(await card("Casa Jardim")).getByRole("button", { name: /Sem e-mail do cliente/ })).toBeInTheDocument();
    expect(within(await card("Conceição")).queryByRole("button", { name: /Sem e-mail do cliente/ })).toBeNull();
    // Only an unsubscribed address: nobody gets them either.
    expect(within(await card("Refúgio")).getByRole("button", { name: /Sem e-mail do cliente/ })).toBeInTheDocument();
    expect(within(await card("Pronto")).queryByRole("button", { name: /Sem e-mail do cliente/ })).toBeNull();
    // Its own dialog, just the addresses, ready to type into.
    await userEvent.click(within(await card("Casa Jardim")).getByRole("button", { name: /Sem e-mail do cliente/ }));
    expect(await screen.findByRole("dialog", { name: "E-mails do cliente" })).toBeInTheDocument();
    expect(screen.getByLabelText("Novo e-mail")).toHaveFocus();
  });

  it("if the types fail to load, offers to try again and blocks creating", async () => {
    let fail = true;
    api(LOCAL, {
      "GET /api/project-types": () => (fail ? { status: 503, body: { error: "unexpected" } } : { body: OPTIONS }),
    });
    renderAt("/");
    await userEvent.click(await screen.findByRole("button", { name: "Novo projeto" }));
    const dialog = await screen.findByRole("dialog");
    const retry = await within(dialog).findByRole("button", { name: "Tentar novamente" });
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
