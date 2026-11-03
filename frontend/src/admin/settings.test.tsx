import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { describe, expect, it } from "vitest";

import { fakeApi } from "../test/render";
import { adminRoutes } from "./AdminApp";
import { moved, sameTexts, type Catalog } from "./siteSettings";

const ME = { email: "fabio@unio.example", csrf_token: "csrf-9", logs_project: null, logs_service: null, actions_enabled: true };

const CATALOG: Catalog = {
  can_change: true,
  limits: { typeLabel: 40, stageTitle: 80, stageAbout: 1000 },
  types: [
    {
      key: "visualization",
      labels: { pt: "Visualização Arquitetônica", en: "Architectural visualization" },
      hidden: false,
      lists_every_stage: false,
      projects: 3,
      stages: [
        { key: "briefing", usual: true, about: { pt: "Conversa sobre as imagens.", en: "A talk." }, projects: 3 },
        { key: "documentation", usual: false, about: null, projects: 1 },
      ],
    },
    { key: "other", labels: { pt: "Outro", en: "Other" }, hidden: false, lists_every_stage: true, projects: 0, stages: [] },
  ],
  stages: [
    { key: "briefing", titles: { pt: "Briefing", en: "Briefing" }, about: { pt: "Conversa inicial.", en: "First talk." }, hidden: false, projects: 9 },
    { key: "documentation", titles: { pt: "Documentação", en: "Documentation" }, about: { pt: "Arquivos.", en: "Files." }, hidden: false, projects: 1 },
    { key: "survey", titles: { pt: "Levantamento", en: "Survey" }, about: { pt: "Medidas.", en: "Measures." }, hidden: true, projects: 0 },
  ],
};

function renderAt(path: string, handlers: Parameters<typeof fakeApi>[0] = {}, catalog: Catalog = CATALOG) {
  const sent = fakeApi({
    "GET /api/admin/me": () => ({ body: ME }),
    "GET /api/admin/settings/types-and-stages": () => ({ body: catalog }),
    ...handlers,
  });
  const router = createMemoryRouter(adminRoutes, { initialEntries: [path] });
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return Object.assign(sent, { router });
}

const body = (sent: { method: string; path: string; body: unknown }[], path: string) =>
  sent.find((r) => r.method !== "GET" && r.path === path)?.body as Record<string, unknown> | undefined;

describe("Configurações (A44)", () => {
  it("is a section of its own beside Escritórios, with its sections at the side and the warning always on", async () => {
    const { router } = renderAt("/configuracoes");
    const tabs = await screen.findByRole("navigation", { name: "Seções do painel de administração" });
    expect(within(tabs).getByRole("link", { name: "Configurações" })).toHaveClass("active");
    expect(within(tabs).getByRole("link", { name: "Escritórios" })).not.toHaveAttribute("aria-current");
    await waitFor(() => expect(router.state.location.pathname).toBe("/configuracoes/tipos"));
    const side = screen.getByRole("navigation", { name: "Seções das configurações" });
    expect(within(side).getAllByRole("link").map((l) => l.textContent)).toEqual(["Tipos de projeto", "Etapas"]);
    expect(screen.getByRole("note")).toHaveTextContent(/valem para todos os escritórios/);
  });

  it("lists the types in order with their stages and projects, and moves one", async () => {
    const sent = renderAt("/configuracoes/tipos", {
      "PUT /api/admin/settings/order": () => ({ body: CATALOG }),
    });
    const visualization = (await screen.findByText("Visualização Arquitetônica")).closest("li")!;
    expect(visualization).toHaveTextContent("2 etapas listadas · 3 projetos");
    expect(screen.getByText("Outro").closest("li")).toHaveTextContent("Todas as etapas");
    expect(within(visualization).getByRole("button", { name: "Subir Visualização Arquitetônica" })).toBeDisabled();
    await userEvent.click(within(visualization).getByRole("button", { name: "Descer Visualização Arquitetônica" }));
    await waitFor(() =>
      expect(body(sent, "/api/admin/settings/order")).toEqual({ kind: "types", keys: ["other", "visualization"] }),
    );
  });

  it("adds a type by its name; English left blank", async () => {
    const sent = renderAt("/configuracoes/tipos", { "POST /api/admin/settings/types": () => ({ body: CATALOG }) });
    const form = await screen.findByRole("region", { name: "Novo tipo" });
    await userEvent.type(within(form).getByLabelText(/Português/), "Restauro");
    await userEvent.click(within(form).getByRole("button", { name: "Adicionar" }));
    await waitFor(() => expect(body(sent, "/api/admin/settings/types")).toEqual({ labels: { pt: "Restauro", en: "" } }));
    expect(await screen.findByText("Tipo “Restauro” criado.")).toBeInTheDocument();
  });

  it("edits a type's stages: listed, ticked and its own words, without a warning when no project's text changes", async () => {
    const sent = renderAt("/configuracoes/tipos/visualization", {
      "PUT /api/admin/settings/types/visualization": () => ({ body: CATALOG }),
    });
    await screen.findByRole("heading", { name: "Visualização Arquitetônica" });
    const survey = screen.getByText("Levantamento").closest("li")!;
    expect(survey).toHaveTextContent("Oculto");
    await userEvent.click(within(survey).getByRole("checkbox", { name: "Listada" }));
    await userEvent.click(within(survey).getByRole("checkbox", { name: "Já vem marcada" }));
    const documentation = screen.getByText("Documentação").closest("li")!;
    await userEvent.click(within(documentation).getByRole("checkbox", { name: "Listada" })); // no longer listed
    await userEvent.click(screen.getByRole("button", { name: "Salvar alterações" }));
    await waitFor(() =>
      expect(body(sent, "/api/admin/settings/types/visualization")).toEqual({
        labels: CATALOG.types[0]!.labels,
        hidden: false,
        stages: [
          { key: "briefing", usual: true, about: { pt: "Conversa sobre as imagens.", en: "A talk." } },
          { key: "survey", usual: true, about: null },
        ],
      }),
    );
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("warns in red, with the projects it changes, before renaming a type or rewriting its words", async () => {
    const sent = renderAt("/configuracoes/tipos/visualization", {
      "PUT /api/admin/settings/types/visualization": () => ({ body: CATALOG }),
    });
    const name = (await screen.findAllByLabelText(/Português/))[0]!;
    await userEvent.clear(name);
    await userEvent.type(name, "Renderização");
    const briefing = screen.getByText("Briefing", { selector: "strong" }).closest("li")!;
    const words = within(briefing).getAllByLabelText(/Português/)[0]!;
    await userEvent.type(words, " E referências.");
    await userEvent.click(screen.getByRole("button", { name: "Salvar alterações" }));
    const warning = await screen.findByRole("alertdialog", { name: "Atenção: esta alteração muda projetos existentes" });
    expect(within(warning).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "⚠ O nome do tipo, em 3 projetos",
      "⚠ A descrição de “Briefing”, em 3 projetos",
    ]);
    // Going back saves nothing; going ahead saves.
    await userEvent.click(within(warning).getByRole("button", { name: "Voltar e revisar" }));
    expect(body(sent, "/api/admin/settings/types/visualization")).toBeUndefined();
    await userEvent.click(screen.getByRole("button", { name: "Salvar alterações" }));
    await userEvent.click(await screen.findByRole("button", { name: "Alterar mesmo assim" }));
    await waitFor(() => expect(body(sent, "/api/admin/settings/types/visualization")?.labels).toEqual({ pt: "Renderização", en: "Architectural visualization" }));
  });

  it("shows a stage's general text until its own words are asked for", async () => {
    const sent = renderAt("/configuracoes/tipos/visualization", {
      "PUT /api/admin/settings/types/visualization": () => ({ body: CATALOG }),
    });
    await screen.findByRole("heading", { name: "Visualização Arquitetônica" });
    const documentation = screen.getByText("Documentação").closest("li")!;
    expect(documentation).toHaveTextContent("Descrição geral: Arquivos.");
    expect(within(documentation).queryByLabelText(/Português/)).toBeNull();
    await userEvent.click(within(documentation).getByRole("button", { name: "Escrever descrição própria" }));
    await userEvent.type(within(documentation).getByLabelText(/Português/), "Os arquivos das imagens.");
    await userEvent.click(screen.getByRole("button", { name: "Salvar alterações" }));
    // Documentação's own words reach its 1 project.
    const warning = await screen.findByRole("alertdialog");
    expect(warning).toHaveTextContent("A descrição de “Documentação”, em 1 projeto");
    await userEvent.click(within(warning).getByRole("button", { name: "Alterar mesmo assim" }));
    await waitFor(() =>
      expect((body(sent, "/api/admin/settings/types/visualization")?.stages as unknown[])[1]).toEqual({
        key: "documentation",
        usual: false,
        about: { pt: "Os arquivos das imagens.", en: "" },
      }),
    );
  });

  it("for Outro, chooses only the ticked stages: it lists every one", async () => {
    renderAt("/configuracoes/tipos/other");
    await screen.findByRole("heading", { name: "Outro" });
    expect(screen.getByText(/lista todas as etapas que não estão ocultas/)).toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: "Listada" })).toBeNull();
    expect(screen.getAllByRole("checkbox", { name: "Já vem marcada" })).toHaveLength(3);
  });

  it("edits a stage, warning how many projects its name and general text reach, and hides one without a warning", async () => {
    const sent = renderAt("/configuracoes/etapas/briefing", {
      "PUT /api/admin/settings/stages/briefing": () => ({ body: CATALOG }),
    });
    await screen.findByRole("heading", { name: "Briefing" });
    const [name, about] = screen.getAllByLabelText(/Português/);
    await userEvent.type(name!, " inicial");
    await userEvent.type(about!, " Mais.");
    await userEvent.click(screen.getByRole("button", { name: "Salvar alterações" }));
    const warning = await screen.findByRole("alertdialog");
    // 9 projects have Briefing; Visualização's 3 show its own words instead.
    expect(within(warning).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "⚠ O nome da etapa, em 9 projetos",
      "⚠ A descrição geral, em até 6 projetos (nos tipos sem descrição própria para esta etapa)",
    ]);
    await userEvent.click(within(warning).getByRole("button", { name: "Voltar e revisar" }));
    await userEvent.clear(name!);
    await userEvent.type(name!, "Briefing");
    await userEvent.clear(about!);
    await userEvent.type(about!, "Conversa inicial.");
    await userEvent.click(screen.getByRole("switch", { name: "Ocultar esta etapa" }));
    await userEvent.click(screen.getByRole("button", { name: "Salvar alterações" }));
    await waitFor(() => expect(body(sent, "/api/admin/settings/stages/briefing")?.hidden).toBe(true));
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("only shows the lists where the operator's login isn't set up", async () => {
    renderAt("/configuracoes/etapas/briefing", {}, { ...CATALOG, can_change: false });
    expect(await screen.findByText(/as listas podem ser vistas, mas não alteradas/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Salvar alterações" })).toBeNull();
    for (const field of screen.getAllByLabelText(/Português/)) expect(field).toBeDisabled();
  });

  it("says when an item no longer exists", async () => {
    renderAt("/configuracoes/etapas/gone");
    const gone = await screen.findByText(/Este item não existe mais/);
    expect(within(gone).getByRole("link", { name: "Etapas" })).toHaveAttribute("href", "/configuracoes/etapas");
  });
});

describe("the lists' helpers", () => {
  it("moves one place, never past either end", () => {
    expect(moved(["a", "b", "c"], "b", -1)).toEqual(["b", "a", "c"]);
    expect(moved(["a", "b", "c"], "c", 1)).toEqual(["a", "b", "c"]);
  });

  it("compares texts as the server keeps them: blank English is the Portuguese", () => {
    expect(sameTexts({ pt: "Briefing", en: "" }, { pt: "Briefing", en: "Briefing" })).toBe(true);
    expect(sameTexts({ pt: "Briefing ", en: "x" }, { pt: "Briefing", en: "y" })).toBe(false);
    expect(sameTexts(null, { pt: "", en: "" })).toBe(true);
  });
});
