import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, onTestFinished, vi } from "vitest";

import { fakeApi, TENANT } from "../test/render";
import * as imageCrop from "../ui/imageCrop";
import { ClientApp, slugFromPath } from "./ClientApp";
import { detailValue, googleCalendarLink, meetingWhen, paragraphs, type Page } from "./format";
import { entriesFor } from "./Updates";
import { shownFiles, sortFiles } from "./FileTools";

// The guided tour (Driver.js) is checked in the browser tests; here, when it starts.
const tour = vi.hoisted(() => ({ startTour: vi.fn() }));
vi.mock("./Tour", () => tour);

// The browser's image decoding and canvas aren't in the test DOM: an image of 1200×800.
vi.mock("../ui/imageCrop", async (original) => ({
  ...(await original<typeof import("../ui/imageCrop")>()),
  loadImage: vi.fn(async () => ({ naturalWidth: 1200, naturalHeight: 800 }) as HTMLImageElement),
  withoutBackground: vi.fn(async () => null),
  cropToFile: vi.fn(async (_image: unknown, _box: unknown, output: { type: string }, name: string) => new File(["x"], name, { type: output.type })),
}));

const PAGE: Page = {
  office: { name: "Alinea", logo_url: null, logo_dark_url: null },
  locale: "pt-BR",
  timezone: "America/Sao_Paulo",
  name: "Casa Jardim",
  client_name: "Família Oliveira",
  project_type: "Projeto Arquitetônico",
  project_type_key: "architecture",
  description: "Residência no alto.\n- Concreto aparente\n- Brises de madeira",
  cover_url: null,
  completed: false,
  current_position: 2,
  last_update: "2026-10-15T23:30:00Z", // 20:30 in São Paulo: still the 15th there
  details: [
    { key: "site_area", label: "Área do terreno", type: "area", value: 1240 },
    { key: "start_date", label: "Início", type: "date", value: "2026-03-02" },
  ],
  stages: [
    { position: 1, title: "Briefing", about: "Necessidades e orçamento.", notes: "" },
    { position: 2, title: "Levantamento", about: "Análise do terreno.", notes: "Medidas conferidas." },
    { position: 3, title: "Estudo Preliminar", about: null, notes: "" },
  ],
  next_meeting: {
    title: "Apresentação",
    starts_at: "2026-10-21T19:00:00Z",
    ends_at: "2026-10-21T20:00:00Z",
    location: "Online",
    link: "https://meet.example/abc",
  },
};

function at(path: string, handlers: Record<string, () => { status?: number; body?: unknown }>) {
  window.history.pushState({}, "", path);
  fakeApi({ "GET /api/tenant": () => ({ body: TENANT }), ...handlers });
  render(<ClientApp />);
}

afterEach(() => vi.unstubAllGlobals());

function phoneViewport() {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: query === "(max-width: 760px)",
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
}

describe("the client page", () => {
  it.each(["", PAGE.description])("shows a mobile description only when supplied: %j", async (description) => {
    phoneViewport();
    at("/casa-jardim", { "GET /api/pages/casa-jardim": () => ({ body: { ...PAGE, description } }) });
    await userEvent.click(await screen.findByText("Detalhes do projeto"));
    const summary = screen.getByText("Detalhes do projeto").closest("details")!;
    expect(summary).toHaveAttribute("open");
    expect(within(summary).getByText(PAGE.client_name.toUpperCase())).toBeVisible();
    if (description) {
      expect(within(summary).getByText("Residência no alto.")).toBeVisible();
    } else {
      expect(within(summary).queryByText("Descrição do projeto")).toBeNull();
    }
  });
  it("shows the project with the current stage open", async () => {
    at("/casa-jardim", { "GET /api/pages/casa-jardim": () => ({ body: PAGE }) });
    expect(await screen.findByRole("heading", { level: 1, name: "Casa Jardim" })).toHaveTextContent("/casa jardim"); // under 15 characters: one line, with a space
    expect(screen.getByText("Medidas conferidas.")).toBeVisible(); // stage 2 is current
    expect(screen.getByText("1.240 m²")).toBeInTheDocument();
    expect(screen.getByText("15/10/2026")).toBeInTheDocument(); // the office's day
    await waitFor(() => expect(document.title).toBe("Casa Jardim · Alinea")); // set after drawing
  });

  it("explains a stage in the project type's words", async () => {
    at("/casa-jardim", { "GET /api/pages/casa-jardim": () => ({ body: PAGE }) });
    await userEvent.click(await screen.findByRole("button", { name: "Sobre esta etapa: Briefing" }));
    expect(screen.getByText("Necessidades e orçamento.")).toBeVisible();
    // A stage without a description has no "Sobre esta etapa".
    expect(screen.queryByRole("button", { name: "Sobre esta etapa: Estudo Preliminar" })).toBeNull();
  });

  it("opens a stage from the timeline", async () => {
    at("/casa-jardim", { "GET /api/pages/casa-jardim": () => ({ body: PAGE }) });
    const timeline = await screen.findByRole("list", { name: "Etapas" });
    Element.prototype.scrollIntoView = vi.fn();
    await userEvent.click(within(timeline).getByRole("button", { name: /Estudo Preliminar/ }));
    const section = document.getElementById("stage-2")!;
    expect(section.className).toContain("is-expanded");
  });

  it("shows the project's type under its title, not among the details", async () => {
    at("/casa-jardim", { "GET /api/pages/casa-jardim": () => ({ body: PAGE }) });
    await screen.findByRole("heading", { level: 1, name: "Casa Jardim" });
    const kind = document.querySelector(".project-kind");
    expect(kind).toHaveTextContent(PAGE.project_type);
    expect(screen.queryByText("Tipo de projeto")).toBeNull();
  });

  it("leaves out an empty description, so nothing sits blank", async () => {
    at("/casa-jardim", { "GET /api/pages/casa-jardim": () => ({ body: { ...PAGE, description: "" } }) });
    await screen.findByRole("heading", { level: 1, name: "Casa Jardim" });
    expect(document.querySelector(".project-layout__desc")).toBeNull();
  });

  it("says when a page doesn't exist, in the office's language", async () => {
    at("/nada", { "GET /api/pages/nada": () => ({ status: 404, body: { error: "page_not_found" } }) });
    expect(await screen.findByRole("heading", { name: "Página não encontrada" })).toBeInTheDocument();
  });

  it("asks for the password on a protected page, then shows it", async () => {
    let unlocked = false;
    let tries = 0;
    window.history.pushState({}, "", "/refugio");
    const sent = fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/pages/refugio": () =>
        unlocked ? { body: { ...PAGE, name: "Refúgio" } } : { status: 403, body: { error: "page_locked" } },
      "POST /api/pages/refugio/unlock": (body: unknown) => {
        tries += 1;
        if ((body as { password: string }).password !== "certa") return { status: 401, body: { error: "wrong_page_password" } };
        unlocked = true;
        return { status: 204 };
      },
    });
    render(<ClientApp />);
    expect(await screen.findByRole("heading", { name: "Página protegida" })).toBeInTheDocument();
    expect(screen.queryByText("Refúgio")).toBeNull();
    await userEvent.type(screen.getByLabelText("Senha"), "errada");
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Senha incorreta.");
    await userEvent.clear(screen.getByLabelText("Senha"));
    await userEvent.type(screen.getByLabelText("Senha"), "certa");
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Refúgio" })).toBeInTheDocument();
    expect(tries).toBe(2);
    expect(sent.filter((r) => r.method === "POST").map((r) => r.body)).toEqual([
      { password: "errada" },
      { password: "certa" },
    ]);
  });

  it("tells a device to wait after too many wrong passwords", async () => {
    at("/refugio", {
      "GET /api/pages/refugio": () => ({ status: 403, body: { error: "page_locked" } }),
      "POST /api/pages/refugio/unlock": () => ({ status: 429, body: { error: "too_many_attempts" } }),
    });
    await userEvent.type(await screen.findByLabelText("Senha"), "qualquer");
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Tente de novo em 15 minutos.");
  });

  it("shows any other failure with its support code, never the server's words", async () => {
    at("/casa", {
      "GET /api/pages/casa": () => ({ status: 500, body: { error: "boom", detail: "Traceback…" } }),
    });
    expect(await screen.findByRole("heading", { name: "Algo deu errado. Tente de novo em instantes." })).toBeInTheDocument();
    expect(screen.queryByText(/Traceback/)).toBeNull();
  });
});

describe("the files", () => {
  it("shows each stage's files, its subfolders as groups, and how many", async () => {
    at("/casa-jardim", {
      "GET /api/pages/casa-jardim": () => ({ body: PAGE }),
      "GET /api/pages/casa-jardim/files": () => ({
        body: {
          stages: [
            { position: 1, groups: [], unavailable: true },
            {
              position: 2,
              groups: [
                { folder: null, files: [{ key: "k1", name: "Planta.pdf", kind: "pdf", size: 2048, modified_at: "2026-10-10T12:00:00Z" }] },
                { folder: "Fotos", files: [{ key: "k2", name: "Terreno.jpg", kind: "image", size: 10, modified_at: "2026-10-11T12:00:00Z" }] },
              ],
            },
            { position: 3, groups: [] },
          ],
        },
      }),
    });
    const current = await screen.findByRole("region", { name: "Levantamento" });
    expect(await within(current).findByRole("button", { name: "Abrir Planta.pdf" })).toBeInTheDocument();
    expect(within(current).getByRole("heading", { name: "Fotos" })).toBeInTheDocument();
    expect(within(current).getByText("02 arquivos")).toBeInTheDocument();
    expect(within(current).getByText("2 KB, 10/10/2026")).toBeInTheDocument();
    const first = screen.getByRole("region", { name: "Briefing" });
    expect(within(first).getByText(/Não foi possível carregar os arquivos/)).toBeInTheDocument();
    const third = screen.getByRole("region", { name: "Estudo Preliminar" });
    expect(within(third).getByText("Ainda sem arquivos nesta etapa.")).toBeInTheDocument();
  });
});

describe("files that can't be listed", () => {
  it("says so in every stage, with the support code, instead of staying blank", async () => {
    at("/casa-jardim", {
      "GET /api/pages/casa-jardim": () => ({ body: PAGE }),
      "GET /api/pages/casa-jardim/files": () => ({
        status: 500,
        body: { error: "unexpected" },
        headers: { "X-Request-ID": "ref42" },
      }),
    });
    const current = await screen.findByRole("region", { name: "Levantamento" });
    expect(await within(current).findByText(/Não foi possível carregar os arquivos.*Código de suporte: ref42/)).toBeInTheDocument();
  });
});

describe("the staff bar", () => {
  it("is only there for the office's staff", async () => {
    at("/casa-jardim", { "GET /api/pages/casa-jardim": () => ({ body: PAGE }) });
    await screen.findByRole("heading", { level: 1, name: "Casa Jardim" });
    expect(screen.queryByRole("navigation", { name: "Ferramentas do escritório" })).toBeNull();
  });

  it("publishes a draft left over (A35), with the CSRF token, and shows it as published", async () => {
    const draft = { ...PAGE, staff: { project_id: "p-1", status: "draft" as const, row_version: 1 } };
    let published = false;
    window.history.pushState({}, "", "/casa-jardim");
    const sent = fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/me": () => ({ body: { csrf_token: "csrf-9" } }),
      "GET /api/pages/casa-jardim": () => ({
        body: published ? { ...draft, staff: { project_id: "p-1", status: "active", row_version: 2 } } : draft,
      }),
      "POST /api/projects/p-1/publish": () => {
        published = true;
        return { body: {} };
      },
    });
    render(<ClientApp />);
    const bar = await screen.findByRole("navigation", { name: "Ferramentas do escritório" });
    expect(within(bar).getByText("Rascunho, só você vê")).toBeInTheDocument();
    await userEvent.click(within(bar).getByRole("button", { name: "Publicar" }));
    expect(await screen.findByText("Publicado. O cliente já pode abrir o link.")).toBeInTheDocument();
    expect(await within(bar).findByText("Publicado")).toBeInTheDocument();
    expect(within(bar).queryByRole("button", { name: "Publicar" })).toBeNull();
    expect(sent.find((r) => r.method === "POST")?.headers.get("X-CSRF-Token")).toBe("csrf-9");
  });

  it("has no publish step: a project is live as soon as it exists", async () => {
    window.history.pushState({}, "", "/casa-jardim");
    fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/me": () => ({ body: { csrf_token: "csrf-9" } }),
      "GET /api/pages/casa-jardim": () => ({
        body: { ...PAGE, staff: { project_id: "p-1", status: "active", row_version: 1 } },
      }),
    });
    render(<ClientApp />);
    const bar = await screen.findByRole("navigation", { name: "Ferramentas do escritório" });
    expect(within(bar).getByText("Publicado")).toBeInTheDocument();
    expect(within(bar).queryByRole("button", { name: "Publicar" })).toBeNull(); // A35
  });
});

describe("edit mode", () => {
  function asStaff(extra: Record<string, (body: unknown) => { status?: number; body?: unknown }> = {}) {
    let version = 4;
    window.history.pushState({}, "", "/casa-jardim");
    const sent = fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/me": () => ({ body: { csrf_token: "csrf-9" } }),
      "GET /api/pages/casa-jardim": () => ({
        body: { ...PAGE, staff: { project_id: "p-1", status: "active", row_version: version } },
      }),
      ...extra,
    });
    render(<ClientApp />);
    return { sent, bump: () => (version += 1) };
  }

  async function startEditing() {
    const bar = await screen.findByRole("navigation", { name: "Ferramentas do escritório" });
    await waitFor(() => expect(within(bar).getByRole("button", { name: "Editar" })).toBeEnabled());
    await userEvent.click(within(bar).getByRole("button", { name: "Editar" }));
  }

  it("in edit mode, a page without a cover offers one in its place, cropped to 3:2", async () => {
    const { sent } = asStaff({
      "GET /api/pages/casa-jardim/files": () => ({ body: { stages: [], updates: [] } }),
      "PUT /api/projects/p-1/cover": () => ({ body: {} }),
    });
    await screen.findByRole("navigation", { name: "Ferramentas do escritório" });
    expect(screen.queryByRole("button", { name: /Adicionar foto de capa/ })).toBeNull(); // not for clients
    await startEditing();
    await userEvent.click(await screen.findByRole("button", { name: /Adicionar foto de capa/ }));
    const input = document.querySelector('.client input[type="file"][hidden]') as HTMLInputElement;
    await userEvent.upload(input, new File(["jpg"], "obra.jpg", { type: "image/jpeg" }));
    const crop = await screen.findByRole("dialog", { name: "Ajustar a capa" });
    await userEvent.click(await within(crop).findByRole("button", { name: "Usar recorte" }));
    expect(await screen.findByText("Capa atualizada.")).toBeInTheDocument();
    expect(sent.some((r) => r.method === "PUT" && r.path === "/api/projects/p-1/cover")).toBe(true);
  });

  it("in edit mode, a cover can be changed from the page", async () => {
    window.history.pushState({}, "", "/casa-jardim");
    fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/me": () => ({ body: { csrf_token: "csrf-9" } }),
      "GET /api/pages/casa-jardim": () => ({
        body: { ...PAGE, cover_url: "/api/pages/casa-jardim/cover?v=1", staff: { project_id: "p-1", status: "active", row_version: 4 } },
      }),
      "GET /api/pages/casa-jardim/files": () => ({ body: { stages: [], updates: [] } }),
    });
    render(<ClientApp />);
    await startEditing();
    expect(await screen.findByRole("button", { name: "Trocar capa" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Adicionar foto de capa/ })).toBeNull();
  });

  it("in edit mode, a cover can be removed from the page", async () => {
    window.history.pushState({}, "", "/casa-jardim");
    const sent = fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/me": () => ({ body: { csrf_token: "csrf-9" } }),
      "GET /api/pages/casa-jardim": () => ({
        body: { ...PAGE, cover_url: "/api/pages/casa-jardim/cover?v=1", staff: { project_id: "p-1", status: "active", row_version: 4 } },
      }),
      "GET /api/pages/casa-jardim/files": () => ({ body: { stages: [], updates: [] } }),
      "DELETE /api/projects/p-1/cover": () => ({ body: {} }),
    });
    render(<ClientApp />);
    await startEditing();
    await userEvent.click(await screen.findByRole("button", { name: "Remover capa" }));
    expect(await screen.findByText("Capa removida.")).toBeInTheDocument();
    expect(sent.some((r) => r.method === "DELETE" && r.path === "/api/projects/p-1/cover")).toBe(true);
  });

  it("starts the page tour once for staff who haven't seen it, and \"?\" replays it", async () => {
    tour.startTour.mockClear();
    window.history.pushState({}, "", "/casa-jardim");
    fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/me": () => ({ body: { csrf_token: "csrf-9", page_tour_seen: false } }),
      "GET /api/pages/casa-jardim": () => ({
        body: { ...PAGE, staff: { project_id: "p-1", status: "active", row_version: 4 } },
      }),
    });
    render(<ClientApp />);
    await waitFor(() => expect(tour.startTour).toHaveBeenCalledTimes(1));
    expect(tour.startTour.mock.calls[0]![0]).toMatchObject({ markSeen: true });
    await userEvent.click(screen.getByRole("button", { name: "Ver o tour da página" }));
    await waitFor(() => expect(tour.startTour).toHaveBeenCalledTimes(2));
    expect(tour.startTour.mock.calls[1]![0]).toMatchObject({ markSeen: false });
  });

  it("doesn't start the tour for staff who've seen it, nor for clients", async () => {
    tour.startTour.mockClear();
    asStaff(); // its /api/me has no page_tour_seen: false
    await screen.findByRole("navigation", { name: "Ferramentas do escritório" });
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(tour.startTour).not.toHaveBeenCalled();
  });

  it("shows no edit controls until staff switch to Editar", async () => {
    asStaff();
    await screen.findByRole("navigation", { name: "Ferramentas do escritório" });
    expect(screen.queryByRole("button", { name: "Editar descrição" })).toBeNull();
    await startEditing();
    expect(screen.getByRole("button", { name: "Editar descrição" })).toBeInTheDocument();
  });

  it("in edit mode, a click on a section's text opens its editor, as its pencil does", async () => {
    asStaff();
    await screen.findByRole("navigation", { name: "Ferramentas do escritório" });
    await userEvent.click(await screen.findByText("Residência no alto."));
    expect(screen.queryByLabelText("Descrição")).toBeNull(); // not for clients
    await startEditing();
    await userEvent.click(screen.getByText("Residência no alto."));
    expect(await screen.findByLabelText("Descrição")).toBeInTheDocument();
    await userEvent.click(document.querySelector("dl.facts[data-opens] dd")!);
    expect(await screen.findByLabelText("Tipo de projeto")).toBeInTheDocument();
  });

  it("in edit mode, the meeting's own links keep their job instead of opening its editor", async () => {
    asStaff();
    await startEditing();
    await userEvent.click(await screen.findByText("Adicionar à agenda"));
    expect(screen.queryByLabelText("Início")).toBeNull();
    await userEvent.click(screen.getByText("Apresentação"));
    expect(await screen.findByLabelText("Início")).toBeInTheDocument();
  });

  it("with no meeting, says so; in edit mode, the card is where to add one", async () => {
    asStaff({
      "GET /api/pages/casa-jardim": () => ({
        body: { ...PAGE, next_meeting: null, staff: { project_id: "p-1", status: "active", row_version: 4 } },
      }),
    });
    expect(await screen.findByText("Nenhuma reunião agendada ainda")).toBeInTheDocument();
    expect(screen.queryByText("Clique aqui para adicionar uma reunião")).toBeNull();
    await startEditing();
    await userEvent.click(screen.getByText("Clique aqui para adicionar uma reunião"));
    expect(await screen.findByLabelText("Início")).toBeInTheDocument();
  });

  it("names the stage the advancer moves on from as the current one", async () => {
    asStaff();
    await startEditing();
    const rail = document.querySelector(".rail__now p")!;
    expect(rail).toHaveTextContent("Etapa atual");
    expect(rail).toHaveTextContent(PAGE.stages[1]!.title);
  });

  it("offers staff an empty description to fill in", async () => {
    phoneViewport();
    asStaff({ "GET /api/pages/casa-jardim": () => ({ body: { ...PAGE, description: "", staff: { project_id: "p-1", status: "active", row_version: 4 } } }) });
    await startEditing();
    expect(await screen.findByRole("button", { name: "Editar descrição" })).toBeInTheDocument();
  });

  it("renames the project from its title, with the page's row version", async () => {
    const { sent } = asStaff({ "PATCH /api/projects/p-1": () => ({ body: {} }) });
    await startEditing();
    await userEvent.click(screen.getByRole("button", { name: "Editar nome do projeto" }));
    const field = await screen.findByLabelText("Nome do projeto");
    await userEvent.clear(field);
    await userEvent.type(field, "Casa Jardim II");
    await userEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await waitFor(() =>
      expect(sent.find((r) => r.method === "PATCH")?.body).toEqual({ row_version: 4, name: "Casa Jardim II" }),
    );
  });

  it("saves the description with the page's row version", async () => {
    const { sent } = asStaff({ "PATCH /api/projects/p-1/content": () => ({ status: 204 }) });
    await startEditing();
    await userEvent.click(screen.getByRole("button", { name: "Editar descrição" }));
    const box = await screen.findByLabelText("Descrição");
    await userEvent.clear(box);
    await userEvent.type(box, "Casa nova.");
    await userEvent.click(screen.getByRole("button", { name: "Salvar" }));
    expect(await screen.findByText("Salvo.")).toBeInTheDocument();
    const request = sent.find((r) => r.method === "PATCH");
    expect(request?.body).toEqual({ row_version: 4, description: "Casa nova." });
    expect(request?.headers.get("X-CSRF-Token")).toBe("csrf-9");
  });

  it("renames the stage now on that row, after stages moved", async () => {
    let moved = false;
    const stages = () =>
      (moved ? [PAGE.stages[1]!, PAGE.stages[0]!, PAGE.stages[2]!] : PAGE.stages).map((stage, i) => ({
        ...stage,
        position: i + 1,
      }));
    window.history.pushState({}, "", "/casa-jardim");
    fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/me": () => ({ body: { csrf_token: "csrf-9" } }),
      "GET /api/pages/casa-jardim": () => ({
        body: { ...PAGE, stages: stages(), staff: { project_id: "p-1", status: "active", row_version: 4 } },
      }),
      "POST /api/projects/p-1/stages/1/move": () => {
        moved = true;
        return { status: 204 };
      },
    });
    render(<ClientApp />);
    await startEditing();
    await userEvent.click(await screen.findByRole("button", { name: "Mover Briefing para baixo" }));
    await userEvent.click(await screen.findByRole("button", { name: "Renomear etapa Levantamento" }));
    expect(screen.getByLabelText("Nome da etapa")).toHaveValue("Levantamento");
  });

  it.each([
    ["active", true],
    ["draft", false],
  ])("at the last stage, offers Concluir projeto only to an active project (%s)", async (status, offered) => {
    window.history.pushState({}, "", "/casa-jardim");
    fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/me": () => ({ body: { csrf_token: "csrf-9" } }),
      "GET /api/pages/casa-jardim": () => ({
        body: { ...PAGE, current_position: PAGE.stages.length, staff: { project_id: "p-1", status, row_version: 4 } },
      }),
    });
    render(<ClientApp />);
    await startEditing();
    expect(await screen.findByText(/Estudo Preliminar/, { selector: ".rail__now p" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Concluir projeto" }) !== null).toBe(offered);
  });

  it("changes the project type with the details, only when it changed", async () => {
    const { sent } = asStaff({
      "GET /api/detail-types": () => ({ body: [] }),
      "GET /api/project-types": () => ({
        body: {
          types: [
            { key: "architecture", label: "Projeto Arquitetônico" },
            { key: "renovation", label: "Projeto de Reforma" },
          ],
        },
      }),
      "PATCH /api/projects/p-1/content": () => ({ status: 204 }),
    });
    await startEditing();
    await userEvent.click(screen.getByRole("button", { name: "Editar informações" }));
    const type = await screen.findByLabelText("Tipo de projeto");
    await screen.findByRole("option", { name: "Projeto de Reforma" });
    await userEvent.selectOptions(type, "renovation");
    await userEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await screen.findByText("Salvo.");
    expect(sent.find((r) => r.method === "PATCH")?.body).toMatchObject({ project_type: "renovation" });
  });

  it("doesn't offer Editar on an archived project", async () => {
    window.history.pushState({}, "", "/casa-jardim");
    fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/me": () => ({ body: { csrf_token: "csrf-9" } }),
      "GET /api/pages/casa-jardim": () => ({
        body: { ...PAGE, staff: { project_id: "p-1", status: "archived", row_version: 4 } },
      }),
    });
    render(<ClientApp />);
    const bar = await screen.findByRole("navigation", { name: "Ferramentas do escritório" });
    const editar = within(bar).getByRole("button", { name: "Editar" });
    expect(editar).toBeDisabled();
    expect(editar).toHaveAttribute("title", expect.stringContaining("desarquive"));
  });

  function stagePage(stages: () => Page["stages"], version: () => number, extra: Parameters<typeof fakeApi>[0] = {}) {
    window.history.pushState({}, "", "/casa-jardim");
    fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/me": () => ({ body: { csrf_token: "csrf-9" } }),
      "GET /api/pages/casa-jardim": () => ({
        body: { ...PAGE, stages: stages(), staff: { project_id: "p-1", status: "active", row_version: version() } },
      }),
      ...extra,
    });
    render(<ClientApp />);
  }

  it("closes the remove confirmation once the stage is gone", async () => {
    let removed = false;
    stagePage(
      () => (removed ? [PAGE.stages[0]!, PAGE.stages[2]!] : PAGE.stages).map((s, i) => ({ ...s, position: i + 1 })),
      () => (removed ? 5 : 4),
      {
        "DELETE /api/projects/p-1/stages/2": () => {
          removed = true;
          return { status: 204 };
        },
      },
    );
    await startEditing();
    await userEvent.click(await screen.findByRole("button", { name: "Remover etapa Levantamento" }));
    const confirm = screen.getByRole("group", { name: "Remover etapa Levantamento" });
    await userEvent.click(within(confirm).getByRole("button", { name: "Remover" }));
    // The row now shows Estudo Preliminar: no confirmation waits one click from removing it.
    await screen.findByRole("button", { name: "Remover etapa Estudo Preliminar" });
    expect(screen.queryByRole("group", { name: /Remover etapa/ })).toBeNull();
  });

  it("keeps stage controls off until the page shows the change", async () => {
    let moved = false;
    stagePage(
      () => PAGE.stages,
      () => 4, // the reload hasn't brought the new version yet
      {
        "POST /api/projects/p-1/stages/1/move": () => {
          moved = true;
          return { status: 204 };
        },
      },
    );
    await startEditing();
    await userEvent.click(await screen.findByRole("button", { name: "Mover Briefing para baixo" }));
    expect(moved).toBe(true);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Mover Levantamento para baixo" })).toBeDisabled(),
    );
  });

  describe("uploads and hiding (A31)", () => {
    const FILES = {
      stages: [
        { position: 1, groups: [] },
        {
          position: 2,
          groups: [{ folder: null, files: [{ key: "k1", name: "Planta.pdf", kind: "pdf", size: 2048, modified_at: "2026-10-10T12:00:00Z" }] }],
        },
        { position: 3, groups: [] },
      ],
    };

    // The browser's own PUT to the upload address: XMLHttpRequest, for progress.
    class FakeXhr {
      static sent: { method: string; url: string; body: unknown }[] = [];
      static answer = 200; // Google's answer to every PUT
      responseText = "";
      upload: { onprogress?: (event: { lengthComputable: boolean; loaded: number; total: number }) => void } = {};
      status = 0;
      onload?: () => void;
      onerror?: () => void;
      private method = "";
      private url = "";
      open(method: string, url: string) {
        this.method = method;
        this.url = url;
      }
      setRequestHeader() {}
      send(body: File) {
        FakeXhr.sent.push({ method: this.method, url: this.url, body });
        this.upload.onprogress?.({ lengthComputable: true, loaded: body.size, total: body.size });
        this.status = FakeXhr.answer;
        this.responseText = this.status >= 400 ? "storageQuotaExceeded" : "";
        setTimeout(() => this.onload?.());
      }
    }

    function asEditor(extra: Parameters<typeof fakeApi>[0] = {}) {
      FakeXhr.sent = [];
      FakeXhr.answer = 200;
      vi.stubGlobal("XMLHttpRequest", FakeXhr);
      return asStaff({ "GET /api/pages/casa-jardim/files": () => ({ body: FILES }), ...extra });
    }

    it("sends a chosen file straight to the address the app opened, then lists again", async () => {
      const { sent } = asEditor({
        "POST /api/projects/p-1/stages/2/uploads": () => ({ body: { upload_url: "https://upload.example/s1" } }),
      });
      await startEditing();
      const stage = screen.getByRole("region", { name: "Levantamento" });
      const file = new File(["%PDF"], "Corte.pdf", { type: "application/pdf" });
      await userEvent.upload(await within(stage).findByLabelText("escolha no computador"), file);
      expect(await screen.findByText("Arquivo enviado.")).toBeInTheDocument();
      expect(sent.find((r) => r.method === "POST")?.body).toEqual({
        row_version: 4,
        name: "Corte.pdf",
        size: 4,
        mime_type: "application/pdf",
      });
      expect(FakeXhr.sent).toEqual([{ method: "PUT", url: "https://upload.example/s1", body: file }]);
      await waitFor(() =>
        expect(sent.filter((r) => r.method === "GET" && r.path === "/api/pages/casa-jardim/files").length).toBe(2),
      );
    });

    it("reports a send that failed for good, and shows the support code", async () => {
      const { sent } = asEditor({
        "POST /api/projects/p-1/stages/2/uploads": () => ({ body: { upload_url: "https://upload.example/s1" } }),
        "POST /api/projects/p-1/stages/2/uploads/failed": () => ({
          status: 502,
          body: { error: "upload_failed" },
          headers: { "X-Request-ID": "ref-77" },
        }),
      });
      FakeXhr.answer = 403; // e.g. the office's Drive is full
      await startEditing();
      const stage = screen.getByRole("region", { name: "Levantamento" });
      await userEvent.upload(
        await within(stage).findByLabelText("escolha no computador"),
        new File(["%PDF"], "Corte.pdf", { type: "application/pdf" }),
      );
      expect(await within(stage).findByRole("alert")).toHaveTextContent(
        "Não foi possível enviar o arquivo. Tente de novo; se continuar, fale com o suporte. Código de suporte: ref-77",
      );
      expect(sent.find((r) => r.path.endsWith("/uploads/failed"))?.body).toEqual({
        name: "Corte.pdf",
        size: 4,
        status: 403,
        detail: "storageQuotaExceeded",
      });
    });

    it("says a file over 100 MB is too large, without opening an upload", async () => {
      const { sent } = asEditor();
      await startEditing();
      const stage = screen.getByRole("region", { name: "Levantamento" });
      const big = new File(["x"], "Video.mp4", { type: "video/mp4" });
      Object.defineProperty(big, "size", { value: 101 * 1024 * 1024 });
      await userEvent.upload(await within(stage).findByLabelText("escolha no computador"), big);
      expect(await within(stage).findByRole("alert")).toHaveTextContent("até 100 MB");
      expect(sent.some((r) => r.method === "POST")).toBe(false);
      expect(FakeXhr.sent).toEqual([]);
    });

    it("hides a file from the client from its menu", async () => {
      const { sent } = asEditor({ "POST /api/pages/casa-jardim/files/k1/hide": () => ({ status: 204 }) });
      await startEditing();
      await userEvent.click(await screen.findByRole("button", { name: "Ações para Planta.pdf" }));
      await userEvent.click(screen.getByRole("menuitem", { name: /Ocultar do cliente/ }));
      expect(await screen.findByText(/não aparece mais para o cliente/)).toBeInTheDocument();
      expect(sent.some((r) => r.method === "POST" && r.path.endsWith("/k1/hide"))).toBe(true);
    });

    it("explains how to hide a file not sent through the site", async () => {
      asEditor({
        "POST /api/pages/casa-jardim/files/k1/hide": () => ({ status: 409, body: { error: "file_not_ours" } }),
      });
      await startEditing();
      await userEvent.click(await screen.findByRole("button", { name: "Ações para Planta.pdf" }));
      await userEvent.click(screen.getByRole("menuitem", { name: /Ocultar do cliente/ }));
      expect(await screen.findByText(/renomeie-o na pasta da etapa começando com _/)).toBeInTheDocument();
    });

    it("moves a file to another stage, offering every stage but its own", async () => {
      const { sent } = asEditor({ "POST /api/pages/casa-jardim/files/k1/move": () => ({ status: 204 }) });
      await startEditing();
      await userEvent.click(await screen.findByRole("button", { name: "Ações para Planta.pdf" }));
      await userEvent.click(screen.getByRole("menuitem", { name: "Mover para outra etapa" }));
      const stages = screen.getByRole("menu", { name: "Mover “Planta.pdf” para" });
      expect(within(stages).getAllByRole("menuitem").map((item) => item.textContent)).toEqual([
        "01 Briefing",
        "03 Estudo Preliminar",
        "Voltar",
      ]); // Planta.pdf is in 02 Levantamento
      await userEvent.click(within(stages).getByRole("menuitem", { name: "03 Estudo Preliminar" }));
      expect(await screen.findByText("“Planta.pdf” foi movido para Estudo Preliminar.")).toBeInTheDocument();
      expect(sent.find((r) => r.path.endsWith("/k1/move"))?.body).toEqual({ position: 3, row_version: 4 });
    });

    it("explains how to move a file not sent through the site", async () => {
      asEditor({
        "POST /api/pages/casa-jardim/files/k1/move": () => ({ status: 409, body: { error: "file_not_ours_to_move" } }),
      });
      await startEditing();
      await userEvent.click(await screen.findByRole("button", { name: "Ações para Planta.pdf" }));
      await userEvent.click(screen.getByRole("menuitem", { name: "Mover para outra etapa" }));
      await userEvent.click(screen.getByRole("menuitem", { name: "01 Briefing" }));
      expect(await screen.findByText(/mova-o para a pasta da outra etapa/)).toBeInTheDocument();
    });

    it("makes an image the cover, and offers it only for images", async () => {
      const image = { key: "k2", name: "Terreno.jpg", kind: "image", size: 10, modified_at: "2026-10-11T12:00:00Z" };
      const withImage = {
        ...FILES,
        stages: [FILES.stages[0], { position: 2, groups: [{ folder: null, files: [...FILES.stages[1]!.groups[0]!.files, image] }] }, FILES.stages[2]],
      };
      const { sent } = asEditor({
        "GET /api/pages/casa-jardim/files": () => ({ body: withImage }),
        "PUT /api/projects/p-1/cover": () => ({ body: {} }),
      });
      await startEditing();
      await userEvent.click(await screen.findByRole("button", { name: "Ações para Planta.pdf" }));
      expect(screen.queryByRole("menuitem", { name: "Definir como capa" })).toBeNull(); // a PDF
      await userEvent.click(screen.getByRole("button", { name: "Ações para Terreno.jpg" }));
      await userEvent.click(screen.getByRole("menuitem", { name: "Definir como capa" }));
      // Cropped to the cover's shape first, from the image on the page.
      const crop = await screen.findByRole("dialog", { name: "Ajustar a capa" });
      expect(imageCrop.loadImage).toHaveBeenCalledWith(expect.stringContaining("/api/pages/casa-jardim/files/k2?inline=true"));
      await userEvent.click(await within(crop).findByRole("button", { name: "Usar recorte" }));
      expect(await screen.findByText("“Terreno.jpg” agora é a capa do projeto.")).toBeInTheDocument();
      expect(sent.some((r) => r.method === "PUT" && r.path === "/api/projects/p-1/cover")).toBe(true);
      expect(imageCrop.cropToFile).toHaveBeenCalledWith(expect.anything(), expect.anything(), imageCrop.COVER_OUTPUT, "capa.jpg");
    });

    it("shows neither to someone viewing as the client", async () => {
      asEditor();
      await screen.findByRole("button", { name: "Abrir Planta.pdf" });
      expect(screen.queryByLabelText("escolha no computador")).toBeNull();
      expect(screen.queryByRole("button", { name: "Ações para Planta.pdf" })).toBeNull();
    });
  });

  it("says when someone else changed the project meanwhile", async () => {
    asStaff({ "PUT /api/projects/p-1/stages/2/notes": () => ({ status: 409, body: { error: "project_changed" } }) });
    await startEditing();
    await userEvent.click(screen.getByRole("button", { name: "Editar recado" }));
    await userEvent.click(await screen.findByRole("button", { name: "Salvar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("alterado por outra pessoa");
  });

  it("schedules the meeting on the office's clock", async () => {
    const { sent } = asStaff({ "PUT /api/projects/p-1/meeting": () => ({ status: 204 }) });
    await startEditing();
    await userEvent.click(screen.getByRole("button", { name: "Editar reunião" }));
    // The existing meeting (19:00 UTC) shows as 16:00, São Paulo's time.
    expect(await screen.findByLabelText("Início")).toHaveValue("16:00");
    expect(screen.getByLabelText("Data")).toHaveValue("2026-10-21");
    await userEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await screen.findByText("Salvo.");
    expect(sent.find((r) => r.method === "PUT")?.body).toMatchObject({
      row_version: 4,
      title: "Apresentação",
      day: "2026-10-21",
      start: "16:00",
      end: "17:00",
    });
  });
});

describe("formatting", () => {
  it("reads the page from the address", () => {
    expect(slugFromPath("/casa-jardim")).toBe("casa-jardim");
    expect(slugFromPath("/casa-jardim/")).toBe("casa-jardim");
  });

  it("shows areas, dates and text as the design does", () => {
    expect(detailValue({ key: "a", label: "Área", type: "area", value: 148.5 }, "pt-BR")).toBe("148,5 m²");
    expect(detailValue({ key: "d", label: "Início", type: "date", value: "2026-03-02" }, "pt-BR")).toBe("02/03/2026");
    expect(detailValue({ key: "l", label: "Local", type: "text", value: "Florianópolis" }, "pt-BR")).toBe("FLORIANÓPOLIS");
  });

  it("puts the meeting in the office's time zone", () => {
    const when = meetingWhen(PAGE.next_meeting!, "pt-BR", "America/Sao_Paulo");
    expect(when).toEqual({ day: "quarta-feira 21/10/2026", time: "16:00 – 17:00" });
  });

  it("fills in Google Calendar's new event", () => {
    const link = new URL(googleCalendarLink(PAGE.next_meeting!, "Casa Jardim", "https://a.example/casa"));
    expect(link.searchParams.get("dates")).toBe("20261021T190000Z/20261021T200000Z");
    expect(link.searchParams.get("text")).toBe("Apresentação · Casa Jardim");
    expect(link.searchParams.get("location")).toBe("Online");
  });

  it("turns '- ' lines into a list", () => {
    expect(paragraphs(PAGE.description)).toEqual([
      { kind: "p", text: "Residência no alto." },
      { kind: "ul", items: ["Concreto aparente", "Brises de madeira"] },
    ]);
  });
});


describe("Atualizações (A28)", () => {
  const update = (id: string, kind: string, stage: number | null, name: string | null = null, at = "2026-10-15T12:00:00Z") => ({
    id,
    kind,
    occurred_at: at,
    stage_position: stage,
    name,
  }) as never;
  const t = (key: string) => key;

  it("words each change as the page shows it now", () => {
    const entries = entriesFor(
      PAGE,
      [
        update("1", "file_published", 2, "Planta.pdf"),
        update("2", "note_changed", 2), // stage 2's note: "Medidas conferidas."
        update("3", "note_changed", 2), // an older note of the same stage: once
        update("4", "meeting_changed", null),
        update("5", "meeting_scheduled", null), // older meeting news: once
        update("6", "stage_advanced", 3), // stage 3 isn't reached (current is 2): left out
        update("7", "stage_advanced", 2),
        update("8", "project_completed", null), // not completed now: left out
        update("9", "note_changed", 1), // stage 1 has no note now: left out
      ],
      t,
      "pt-BR",
    );
    expect(entries.map((e) => [e.title, e.context, e.target])).toEqual([
      ["Planta.pdf", "02 Levantamento", 1],
      ["updates.note", "Medidas conferidas.", 1],
      ["updates.meetingChanged", expect.stringContaining("Apresentação"), "meeting"],
      ["updates.advanced", "02 Levantamento", 1],
    ]);
  });

  it("says a meeting was cancelled when there is none now", () => {
    const entries = entriesFor({ ...PAGE, next_meeting: null }, [update("1", "meeting_cleared", null, "Visita")], t, "pt-BR");
    expect(entries.map((e) => [e.title, e.context, e.target])).toEqual([["updates.meetingCancelled", "Visita", null]]);
  });

  it("shows how many are unread, opens a stage, and remembers what was read", async () => {
    localStorage.clear();
    const files = {
      stages: [],
      updates: [update("u1", "file_published", 1, "Briefing.pdf"), update("u2", "note_changed", 2)],
    };
    at("/casa-jardim", {
      "GET /api/pages/casa-jardim": () => ({ body: PAGE }),
      "GET /api/pages/casa-jardim/files": () => ({ body: files }),
    });
    const bell = await screen.findByLabelText("Últimas atualizações, 2 não lidas");
    await userEvent.click(bell);
    const panel = screen.getByRole("region", { name: "Últimas atualizações" });
    await userEvent.click(within(panel).getAllByRole("button", { name: /Ver etapa/ })[0]!);
    expect(screen.getByRole("button", { name: "Etapa aberta: Briefing" })).toBeInTheDocument(); // stage 1 now open
    await userEvent.click(bell);
    await userEvent.click(within(panel).getByRole("button", { name: "Marcar todas como lidas" }));
    expect(screen.getByLabelText("Últimas atualizações, nenhuma não lida")).toBeInTheDocument();
    expect(JSON.parse(localStorage.getItem("updates-read:casa-jardim")!)).toEqual(["u1", "u2"]);
  });

  it("says when there is nothing yet", async () => {
    at("/casa-jardim", {
      "GET /api/pages/casa-jardim": () => ({ body: PAGE }),
      "GET /api/pages/casa-jardim/files": () => ({ body: { stages: [], updates: [] } }),
    });
    await userEvent.click(await screen.findByLabelText("Últimas atualizações, nenhuma não lida"));
    expect(screen.getByText(/Ainda não há atualizações/)).toBeInTheDocument();
  });
});

describe("the page's file tools", () => {
  const file = (key: string, name: string, kind: string, at: string) =>
    ({ key, name, kind, size: 10, modified_at: at }) as never;
  const FILES = {
    stages: [
      { position: 1, groups: [{ folder: null, files: [file("a", "Programa.pdf", "pdf", "2026-10-01T12:00:00Z")] }] },
      {
        position: 2,
        groups: [
          {
            folder: null,
            files: [
              file("b", "Planta baixa.pdf", "pdf", "2026-10-05T12:00:00Z"),
              file("c", "Implantação.dwg", "other", "2026-10-09T12:00:00Z"),
              file("d", "Terreno.jpg", "image", "2026-10-02T12:00:00Z"),
            ],
          },
        ],
      },
      { position: 3, groups: [] },
    ],
    updates: [],
  };

  it("sorts by date, newest first, by type, or by name", () => {
    const files = FILES.stages[1]!.groups[0]!.files as never[];
    const names = (sort: "updated" | "type" | "name") => sortFiles(files, sort).map((f: { name: string }) => f.name);
    expect(names("updated")).toEqual(["Implantação.dwg", "Planta baixa.pdf", "Terreno.jpg"]);
    expect(names("type")).toEqual(["Implantação.dwg", "Terreno.jpg", "Planta baixa.pdf"]);
    expect(names("name")).toEqual(["Implantação.dwg", "Planta baixa.pdf", "Terreno.jpg"]);
  });

  it("finds files by name or by their stage, without minding accents or case", () => {
    const stage = FILES.stages[1] as never;
    const prefs = { type: "all", sort: "name", view: "grid" } as const;
    expect(shownFiles(stage, "Levantamento", "implantacao", prefs).count).toBe(1);
    expect(shownFiles(stage, "Levantamento", "LEVANTAMENTO", prefs).count).toBe(3);
    expect(shownFiles(stage, "Levantamento", "", { ...prefs, type: "pdf" }).count).toBe(1);
    expect(shownFiles(stage, "Levantamento", "", { ...prefs, type: "dwg" }).count).toBe(1);
  });

  it("searching hides stages without a match and says how many were found", async () => {
    localStorage.clear();
    at("/casa-jardim", {
      "GET /api/pages/casa-jardim": () => ({ body: PAGE }),
      "GET /api/pages/casa-jardim/files": () => ({ body: FILES }),
    });
    await userEvent.type(await screen.findByLabelText("Pesquisar arquivos"), "baixa"); // "planta" would also find "Implantação"
    expect(screen.getByText("1 arquivo encontrado")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Levantamento" })).toBeVisible();
    expect(screen.queryByRole("region", { name: "Briefing" })).toBeNull(); // hidden
  });

  it("a stage chosen in the timeline shows even when the search hid it", async () => {
    localStorage.clear();
    at("/casa-jardim", {
      "GET /api/pages/casa-jardim": () => ({ body: PAGE }),
      "GET /api/pages/casa-jardim/files": () => ({ body: FILES }),
    });
    const search = await screen.findByLabelText("Pesquisar arquivos");
    await userEvent.type(search, "baixa");
    expect(screen.queryByRole("region", { name: "Briefing" })).toBeNull();
    Element.prototype.scrollIntoView = vi.fn();
    const timeline = screen.getByRole("list", { name: "Etapas" });
    await userEvent.click(within(timeline).getByRole("button", { name: /Briefing/ }));
    expect(screen.getByRole("region", { name: "Briefing" })).toBeVisible();
    expect(search).toHaveValue(""); // the search let go, so nothing stays hidden
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
  });

  it("on a phone, never shares a file that's no longer there", async () => {
    const share = vi.fn();
    Object.assign(navigator, { canShare: () => true, share });
    const matchMedia = window.matchMedia;
    window.matchMedia = ((query: string) => ({
      media: query,
      matches: query === "(pointer: coarse)", // a touch screen
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
    })) as never;
    onTestFinished(() => {
      window.matchMedia = matchMedia;
      Object.assign(navigator, { canShare: undefined, share: undefined });
    });
    let status = 404; // removed, moved, or its address expired while the page stayed open
    at("/casa-jardim", {
      "GET /api/pages/casa-jardim": () => ({ body: PAGE }),
      "GET /api/pages/casa-jardim/files": () => ({ body: FILES }),
      "GET /api/pages/casa-jardim/files/d": () => ({ status, body: "não encontrado" }),
    });
    await userEvent.click(await screen.findByRole("button", { name: "Abrir Terreno.jpg" }));
    const preview = screen.getByRole("dialog", { name: "Terreno.jpg" });
    await userEvent.click(within(preview).getByRole("button", { name: "Salvar" }));
    expect(share).not.toHaveBeenCalled(); // the page's own message shows instead
    status = 200;
    await userEvent.click(within(preview).getByRole("button", { name: "Salvar" }));
    await waitFor(() => expect(share).toHaveBeenCalled());
  });

  it("sends a file as the page's address at that file", async () => {
    at("/casa-jardim", {
      "GET /api/pages/casa-jardim": () => ({ body: PAGE }),
      "GET /api/pages/casa-jardim/files": () => ({ body: FILES }),
    });
    await userEvent.click(await screen.findByRole("button", { name: "Abrir Terreno.jpg" }));
    const preview = screen.getByRole("dialog", { name: "Terreno.jpg" });
    await userEvent.click(within(preview).getByRole("button", { name: "Enviar" }));
    const whatsapp = within(preview).getByRole("link", { name: "WhatsApp" }).getAttribute("href")!;
    // By its stage and name: a file's key expires, and Drive's ids stay off the page.
    expect(decodeURIComponent(whatsapp)).toContain(`${window.location.origin}/casa-jardim?etapa=2&arquivo=Terreno.jpg`);
  });

  it("a file's address opens its stage, at the file, with its preview open", async () => {
    Element.prototype.scrollIntoView = vi.fn();
    at("/casa-jardim?etapa=1&arquivo=Programa.pdf", {
      "GET /api/pages/casa-jardim": () => ({ body: PAGE }),
      "GET /api/pages/casa-jardim/files": () => ({ body: FILES }),
    });
    // "Programa.pdf" is in Briefing, not the current stage.
    const preview = await screen.findByRole("dialog", { name: "Programa.pdf" });
    expect(screen.getByRole("button", { name: "Etapa aberta: Briefing" })).toBeInTheDocument();
    await waitFor(() => expect(Element.prototype.scrollIntoView).toHaveBeenCalled());
    await userEvent.click(within(preview).getByRole("button", { name: "Fechar" }));
    expect(window.location.search).toBe(""); // closed: reloading shows the page as usual
  });

  it("a file's address for a file no longer there shows the page as usual", async () => {
    at("/casa-jardim?etapa=2&arquivo=Programa.pdf", { // renamed, moved or removed
      "GET /api/pages/casa-jardim": () => ({ body: PAGE }),
      "GET /api/pages/casa-jardim/files": () => ({ body: FILES }),
    });
    expect(await screen.findByRole("button", { name: "Abrir Terreno.jpg" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("a file's address finds it in a second subfolder of the same name", async () => {
    const other = file("e", "Corte.pdf", "pdf", "2026-10-03T12:00:00Z");
    const stages = [
      // Drive allows sibling folders with the same name.
      { position: 1, groups: [{ folder: "Revisão", files: FILES.stages[0]!.groups[0]!.files }, { folder: "Revisão", files: [other] }] },
      ...FILES.stages.slice(1),
    ];
    at("/casa-jardim?etapa=1&pasta=Revis%C3%A3o&arquivo=Corte.pdf", {
      "GET /api/pages/casa-jardim": () => ({ body: PAGE }),
      "GET /api/pages/casa-jardim/files": () => ({ body: { ...FILES, stages } }),
    });
    expect(await screen.findByRole("dialog", { name: "Corte.pdf" })).toBeInTheDocument();
  });

  it("a file's address names its subfolder, so a file of the same name elsewhere isn't opened", async () => {
    const twin = file("e", "Programa.pdf", "image", "2026-10-03T12:00:00Z");
    const stages = [
      { position: 1, groups: [FILES.stages[0]!.groups[0], { folder: "Revisão", files: [twin] }] },
      ...FILES.stages.slice(1),
    ];
    at("/casa-jardim?etapa=1&pasta=Revis%C3%A3o&arquivo=Programa.pdf", {
      "GET /api/pages/casa-jardim": () => ({ body: PAGE }),
      "GET /api/pages/casa-jardim/files": () => ({ body: { ...FILES, stages } }),
    });
    const preview = await screen.findByRole("dialog", { name: "Programa.pdf" });
    expect(within(preview).getByRole("img")).toHaveAttribute("src", expect.stringContaining("/files/e")); // the image one
    await userEvent.click(within(preview).getByRole("button", { name: "Enviar" }));
    const whatsapp = within(preview).getByRole("link", { name: "WhatsApp" }).getAttribute("href")!;
    expect(decodeURIComponent(whatsapp)).toContain("?etapa=1&pasta=Revis%C3%A3o&arquivo=Programa.pdf");
  });

  it("while searching, a stage whose files couldn't be read still says so", async () => {
    localStorage.clear();
    const stages = [...FILES.stages.slice(0, 2), { position: 3, groups: [], unavailable: true }];
    at("/casa-jardim", {
      "GET /api/pages/casa-jardim": () => ({ body: PAGE }),
      "GET /api/pages/casa-jardim/files": () => ({ body: { ...FILES, stages } }),
    });
    await userEvent.type(await screen.findByLabelText("Pesquisar arquivos"), "baixa");
    expect(screen.queryByRole("region", { name: "Briefing" })).toBeNull(); // no match: hidden
    const unread = screen.getByRole("region", { name: "Estudo Preliminar" });
    expect(within(unread).getByText(/Não foi possível carregar os arquivos/)).toBeVisible();
  });

  it("while searching, a stage with matches can still be closed", async () => {
    localStorage.clear();
    at("/casa-jardim", {
      "GET /api/pages/casa-jardim": () => ({ body: PAGE }),
      "GET /api/pages/casa-jardim/files": () => ({ body: FILES }),
    });
    const search = await screen.findByLabelText("Pesquisar arquivos");
    await userEvent.type(search, "baixa");
    await userEvent.click(screen.getByRole("button", { name: "Etapa aberta: Levantamento" }));
    expect(screen.getByRole("button", { name: "Abrir etapa Levantamento" })).toHaveAttribute("aria-expanded", "false");
    // A new search opens every match again.
    await userEvent.clear(search);
    await userEvent.type(search, "planta");
    expect(screen.getByRole("button", { name: "Etapa aberta: Levantamento" })).toBeInTheDocument();
  });

  it("an image that won't load shows the file's card, not a broken image", async () => {
    at("/casa-jardim", {
      "GET /api/pages/casa-jardim": () => ({ body: PAGE }),
      "GET /api/pages/casa-jardim/files": () => ({ body: FILES }),
    });
    await userEvent.click(await screen.findByRole("button", { name: "Abrir Terreno.jpg" }));
    const preview = screen.getByRole("dialog", { name: "Terreno.jpg" });
    fireEvent.error(within(preview).getByRole("img", { name: "Terreno.jpg" }));
    expect(within(preview).queryByRole("img")).toBeNull();
    expect(within(preview).getByRole("link", { name: "Abrir original" })).toBeInTheDocument();
  });

  it("a stage chosen in the updates shows even when the search hid it", async () => {
    localStorage.clear();
    const news = { id: "u1", kind: "file_published", occurred_at: "2026-10-15T12:00:00Z", stage_position: 1, name: "Programa.pdf" };
    at("/casa-jardim", {
      "GET /api/pages/casa-jardim": () => ({ body: PAGE }),
      "GET /api/pages/casa-jardim/files": () => ({ body: { ...FILES, updates: [news] } }),
    });
    await userEvent.type(await screen.findByLabelText("Pesquisar arquivos"), "baixa");
    expect(screen.queryByRole("region", { name: "Briefing" })).toBeNull();
    Element.prototype.scrollIntoView = vi.fn();
    await userEvent.click(screen.getByLabelText("Últimas atualizações, 1 não lida"));
    const panel = screen.getByRole("region", { name: "Últimas atualizações" });
    await userEvent.click(within(panel).getByRole("button", { name: /Ver etapa/ }));
    expect(screen.getByRole("region", { name: "Briefing" })).toBeVisible();
  });

  it("switches to a list, and remembers it", async () => {
    localStorage.clear();
    at("/casa-jardim", {
      "GET /api/pages/casa-jardim": () => ({ body: PAGE }),
      "GET /api/pages/casa-jardim/files": () => ({ body: FILES }),
    });
    await userEvent.click(await screen.findByRole("button", { name: "Visualizar em lista" }));
    expect(document.querySelector(".files")).toHaveAttribute("data-view", "list");
    expect(JSON.parse(localStorage.getItem("file-prefs")!)).toMatchObject({ view: "list" });
  });

  it("opens a file's preview, with its actions", async () => {
    at("/casa-jardim", {
      "GET /api/pages/casa-jardim": () => ({ body: PAGE }),
      "GET /api/pages/casa-jardim/files": () => ({ body: FILES }),
    });
    await userEvent.click(await screen.findByRole("button", { name: "Abrir Terreno.jpg" }));
    const preview = screen.getByRole("dialog", { name: "Terreno.jpg" });
    expect(within(preview).getByRole("img", { name: "Terreno.jpg" })).toHaveAttribute(
      "src",
      "/api/pages/casa-jardim/files/d?inline=true",
    );
    expect(within(preview).getByRole("link", { name: "Abrir original" })).toHaveAttribute(
      "href",
      "/api/pages/casa-jardim/files/d?inline=true",
    );
    await userEvent.click(within(preview).getByRole("button", { name: "Enviar" }));
    const whatsapp = within(preview).getByRole("link", { name: "WhatsApp" });
    // The page's address, not the file's (which works only for a while).
    expect(decodeURIComponent(whatsapp.getAttribute("href")!)).toContain(`${window.location.origin}/casa-jardim`);
    await userEvent.click(within(preview).getByRole("button", { name: "Fechar" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
