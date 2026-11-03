// A new project's setup steps on its page (trial, 1 Nov 2026), after the
// painel's "Novo projeto" asked only for the name, client and address.
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, TENANT } from "../test/render";
import { ClientApp } from "./ClientApp";
import type { Page } from "./format";

const tour = vi.hoisted(() => ({ startTour: vi.fn() }));
vi.mock("./Tour", () => tour);

// The browser's image decoding and canvas aren't in the test DOM: an image of 1200×800.
vi.mock("../ui/imageCrop", async (original) => ({
  ...(await original<typeof import("../ui/imageCrop")>()),
  loadImage: vi.fn(async () => ({ naturalWidth: 1200, naturalHeight: 800 }) as HTMLImageElement),
  withoutBackground: vi.fn(async () => null),
  cropToFile: vi.fn(async (_image: unknown, _box: unknown, output: { type: string }, name: string) => new File(["x"], name, { type: output.type })),
}));

afterEach(() => {
  vi.unstubAllGlobals();
  tour.startTour.mockClear();
});

// Just created: the first type, no stages, nothing else yet.
const NEW: Page = {
  id: "6f1c1d1e-0000-4000-8000-0000000000b1",
  office: { name: "Alinea", logo_url: null, logo_dark_url: null },
  team: [],
  locale: "pt-BR",
  timezone: "America/Sao_Paulo",
  name: "Casa do Lago",
  client_name: "Família Souza",
  project_type: "Projeto Arquitetônico",
  project_type_key: "architecture",
  description: "",
  cover_url: null,
  features: [],
  completed: false,
  current_position: null,
  last_update: "2026-11-01T12:00:00Z",
  details: [],
  stages: [],
  next_meeting: null,
  in_proposal: false,
  proposal: null,
  proposal_url: null,
  staff: { project_id: "p-1", status: "active", row_version: 1, recipients: [] },
};

const OPTIONS = {
  types: [
    { key: "architecture", label: "Projeto Arquitetônico", stages: ["briefing", "permit_documents"], offered: ["briefing", "permit_documents", "detailing"] },
    { key: "interiors", label: "Projeto de Interiores", stages: ["briefing", "detailing"], offered: ["briefing", "detailing"] },
  ],
  stages: [
    { key: "briefing", title: "Briefing" },
    { key: "permit_documents", title: "Projeto Legal" },
    { key: "detailing", title: "Detalhamentos" },
  ],
};

const STAFF_ME = { name: "Ana", email: "ana@alinea.example", csrf_token: "csrf-9", page_tour_seen: false };

function arrive(handlers: Record<string, (body?: unknown) => { status?: number; body?: unknown }> = {}, path = "/casa-do-lago?configurar") {
  window.history.pushState({}, "", path);
  const sent = fakeApi({
    "GET /api/tenant": () => ({ body: TENANT }),
    "GET /api/me": () => ({ body: STAFF_ME }),
    "GET /api/pages/casa-do-lago": () => ({ body: NEW }),
    "GET /api/pages/casa-do-lago/files": () => ({ body: { stages: [], updates: [] } }),
    "GET /api/project-types": () => ({ body: OPTIONS }),
    "GET /api/detail-types": () => ({
      body: [
        { key: "location", label: "Localização", type: "text" },
        { key: "site_area", label: "Área do terreno", type: "area" },
      ],
    }),
    ...handlers,
  });
  render(<ClientApp />);
  return sent;
}

const writes = (sent: ReturnType<typeof fakeApi>) => sent.filter((r) => r.method !== "GET");

describe("a new project's setup steps", () => {
  it("open over the page straight from Novo projeto, once, and hold the tour back", async () => {
    arrive();
    const dialog = await screen.findByRole("dialog", { name: "Etapas" });
    expect(within(dialog).getByRole("progressbar", { name: "Passo 1 de 3" })).toBeInTheDocument();
    // A reload of the address doesn't open them again.
    expect(window.location.search).toBe("");
    expect(tour.startTour).not.toHaveBeenCalled();
    await userEvent.click(within(dialog).getByRole("button", { name: "Fechar" }));
    await waitFor(() => expect(tour.startTour).toHaveBeenCalled()); // now, after them
  });

  it("aren't offered to a client opening the same address", async () => {
    arrive({ "GET /api/me": () => ({ status: 401, body: { error: "not_signed_in" } }), "GET /api/pages/casa-do-lago": () => ({ body: { ...NEW, staff: null } }) });
    expect(await screen.findByRole("heading", { level: 1, name: "Casa do Lago" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("list the type's stages, its usual ones ticked, and add them one at a time, in order", async () => {
    const sent = arrive({ "POST /api/projects/p-1/stages": () => ({ status: 204 }) });
    const dialog = await screen.findByRole("dialog", { name: "Etapas" });
    // The type was chosen at creation: no choosing it here.
    expect(within(dialog).queryByRole("radio")).toBeNull();
    expect(await within(dialog).findByRole("checkbox", { name: "Projeto Legal" })).toBeChecked();
    expect(within(dialog).getByRole("checkbox", { name: "Detalhamentos" })).not.toBeChecked(); // suits it, not usual
    await userEvent.click(within(dialog).getByText("Detalhamentos"));
    await userEvent.click(within(dialog).getByText("Projeto Legal")); // untick
    await userEvent.type(within(dialog).getByLabelText(/Outra etapa/), "Maquete{Enter}");
    await userEvent.click(within(dialog).getByRole("button", { name: "Continuar" }));

    expect(await screen.findByRole("dialog", { name: "Descrição e informações" })).toBeInTheDocument();
    expect(writes(sent).map((r) => [r.path, r.body])).toEqual([
      ["/api/projects/p-1/stages", { row_version: 1, builtin_key: "briefing" }],
      ["/api/projects/p-1/stages", { row_version: 2, builtin_key: "detailing" }],
      ["/api/projects/p-1/stages", { row_version: 3, title: "Maquete" }],
    ]);
  });

  it("list the project's own type's stages even when that type is hidden for new projects (A44)", async () => {
    const hidden = { ...OPTIONS, types: [OPTIONS.types[1], { ...OPTIONS.types[0], hidden: true }] };
    arrive({ "GET /api/project-types": () => ({ body: hidden }) });
    const dialog = await screen.findByRole("dialog", { name: "Etapas" });
    // Projeto Arquitetônico's usual stages, not the first type's (Interiores).
    expect(await within(dialog).findByRole("checkbox", { name: "Projeto Legal" })).toBeChecked();
    expect(within(dialog).getByRole("checkbox", { name: "Detalhamentos" })).not.toBeChecked();
  });

  it("list only the stages that suit the type, the rest a click away", async () => {
    arrive({ "GET /api/pages/casa-do-lago": () => ({ body: { ...NEW, project_type_key: "interiors" } }) });
    const dialog = await screen.findByRole("dialog", { name: "Etapas" });
    expect(await within(dialog).findByRole("checkbox", { name: "Detalhamentos" })).toBeChecked();
    expect(within(dialog).queryByRole("checkbox", { name: "Projeto Legal" })).toBeNull();
    await userEvent.click(within(dialog).getByRole("button", { name: "Mostrar todas as etapas" }));
    expect(within(dialog).getByRole("checkbox", { name: "Projeto Legal" })).not.toBeChecked();
  });

  it("after an accepted proposal, make its services the stages, one each", async () => {
    const sent = arrive({
      "GET /api/pages/casa-do-lago": () => ({ body: { ...NEW, proposal_url: "/api/pages/casa-do-lago/proposal.pdf?v=2" } }),
      "GET /api/projects/p-1/proposal": () => ({
        body: { start: { services: [{ title: "Detalhamento executivo" }, { title: "Imagens renderizadas" }] } },
      }),
      "POST /api/projects/p-1/stages": () => ({ status: 204 }),
    });
    const dialog = await screen.findByRole("dialog", { name: "Etapas" });
    expect(within(dialog).getByText(/Cada serviço da proposta vira uma etapa/)).toBeInTheDocument();
    expect(await within(dialog).findByText("2 etapas marcadas.")).toBeInTheDocument(); // not "the type's"
    // A matching stage, and the office's own for the other; the type's usual ones not.
    expect(await within(dialog).findByRole("checkbox", { name: "Imagens renderizadas" })).toBeChecked();
    expect(within(dialog).getByRole("checkbox", { name: "Detalhamentos" })).toBeChecked();
    expect(within(dialog).getByRole("checkbox", { name: "Briefing" })).not.toBeChecked();
    expect(within(dialog).getByRole("checkbox", { name: "Projeto Legal" })).not.toBeChecked();
    await userEvent.click(within(dialog).getByText("Briefing")); // staff still choose
    await userEvent.click(within(dialog).getByRole("button", { name: "Continuar" }));
    expect(await screen.findByRole("dialog", { name: "Descrição e informações" })).toBeInTheDocument();
    expect(writes(sent).map((r) => r.body)).toEqual([
      { row_version: 1, builtin_key: "briefing" },
      { row_version: 2, builtin_key: "detailing" },
      { row_version: 3, title: "Imagens renderizadas" },
    ]);
  });

  it("don't add again a stage the project already has (a proposal from before 2 Nov 2026)", async () => {
    const sent = arrive({
      "GET /api/pages/casa-do-lago": () => ({
        body: {
          ...NEW,
          proposal_url: "/api/pages/casa-do-lago/proposal.pdf?v=2",
          stages: [{ position: 1, title: "Briefing", about: null, notes: "", completed: false }],
        },
      }),
      "GET /api/projects/p-1/proposal": () => ({
        body: { start: { services: [{ title: "Briefing" }, { title: "Projeto Legal" }] } },
      }),
      "POST /api/projects/p-1/stages": () => ({ status: 204 }),
    });
    const dialog = await screen.findByRole("dialog", { name: "Etapas" });
    expect(await within(dialog).findByRole("checkbox", { name: "Projeto Legal" })).toBeChecked();
    await userEvent.click(within(dialog).getByRole("button", { name: "Continuar" }));
    expect(await screen.findByRole("dialog", { name: "Descrição e informações" })).toBeInTheDocument();
    expect(writes(sent).map((r) => r.body)).toEqual([{ row_version: 1, builtin_key: "permit_documents" }]);
  });

  it("can be skipped when the types can't load", async () => {
    arrive({ "GET /api/project-types": () => ({ status: 503, body: { error: "unexpected" } }) });
    const dialog = await screen.findByRole("dialog", { name: "Etapas" });
    await within(dialog).findByText("Não foi possível concluir a ação. Tente novamente em instantes.");
    expect(within(dialog).getByRole("button", { name: "Continuar" })).toBeDisabled();
    await userEvent.click(within(dialog).getByRole("button", { name: "Pular" }));
    expect(await screen.findByRole("dialog", { name: "Descrição e informações" })).toBeInTheDocument();
  });

  it("skipped after a failure part way, go on with the version the stages made left", async () => {
    let calls = 0;
    const sent = arrive({
      "POST /api/projects/p-1/stages": () => (++calls === 2 ? { status: 503, body: { error: "drive_connect_failed" } } : { status: 204 }),
      "PATCH /api/projects/p-1/content": () => ({ status: 204 }),
    });
    const stages = await screen.findByRole("dialog", { name: "Etapas" });
    await within(stages).findByRole("checkbox", { name: "Briefing" });
    await userEvent.click(within(stages).getByRole("button", { name: "Continuar" }));
    await within(stages).findByRole("alert");
    await userEvent.click(within(stages).getByRole("button", { name: "Pular" })); // Briefing was made
    const details = await screen.findByRole("dialog", { name: "Descrição e informações" });
    await userEvent.type(within(details).getByLabelText("Descrição"), "Casa de campo.");
    await userEvent.click(within(details).getByRole("button", { name: "Continuar" }));
    await screen.findByRole("dialog", { name: "E-mails do cliente" });
    expect(sent.find((r) => r.method === "PATCH")?.body).toMatchObject({ row_version: 2 });
  });

  it("reload the page behind when closed, so it has what was saved so far", async () => {
    const sent = arrive();
    const dialog = await screen.findByRole("dialog", { name: "Etapas" });
    const loads = () => sent.filter((r) => r.method === "GET" && r.path === "/api/pages/casa-do-lago").length;
    const before = loads();
    await userEvent.click(within(dialog).getByRole("button", { name: "Fechar" }));
    await waitFor(() => expect(loads()).toBe(before + 1));
  });

  it("refuse an own stage named like one listed", async () => {
    arrive();
    const dialog = await screen.findByRole("dialog", { name: "Etapas" });
    await within(dialog).findByRole("checkbox", { name: "Briefing" });
    await userEvent.type(within(dialog).getByLabelText(/Outra etapa/), "briefing{Enter}");
    expect(within(dialog).getByRole("alert")).toHaveTextContent("Já existe uma etapa chamada “briefing”.");
  });

  it("after a failure part way, a retry adds only the stages still missing", async () => {
    let calls = 0;
    const sent = arrive({
      "POST /api/projects/p-1/stages": () => (++calls === 2 ? { status: 503, body: { error: "drive_connect_failed" } } : { status: 204 }),
    });
    const dialog = await screen.findByRole("dialog", { name: "Etapas" });
    await within(dialog).findByRole("checkbox", { name: "Briefing" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Continuar" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Não foi possível conectar o Google Drive");
    await userEvent.click(within(dialog).getByRole("button", { name: "Continuar" }));
    expect(await screen.findByRole("dialog", { name: "Descrição e informações" })).toBeInTheDocument();
    // Briefing once, Projeto Legal twice (failed, then sent again).
    expect(writes(sent).map((r) => r.body)).toEqual([
      { row_version: 1, builtin_key: "briefing" },
      { row_version: 2, builtin_key: "permit_documents" },
      { row_version: 2, builtin_key: "permit_documents" },
    ]);
  });

  it("save the description, details and client's emails with the version each step left", async () => {
    const sent = arrive({
      "POST /api/projects/p-1/stages": () => ({ status: 204 }),
      "PATCH /api/projects/p-1/content": () => ({ status: 204 }),
      "PATCH /api/projects/p-1": () => ({ body: { row_version: 6 } }),
    });
    let dialog = await screen.findByRole("dialog", { name: "Etapas" });
    await within(dialog).findByRole("checkbox", { name: "Briefing" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Continuar" })); // 2 stages: version 3

    dialog = await screen.findByRole("dialog", { name: "Descrição e informações" });
    await userEvent.type(within(dialog).getByLabelText("Descrição"), "Casa de campo.");
    await userEvent.click(await within(dialog).findByRole("button", { name: /Adicionar detalhes/ }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Localização" }));
    await userEvent.type(within(dialog).getByLabelText("Localização"), "Nova Lima");
    await userEvent.click(within(dialog).getByRole("button", { name: "Continuar" }));

    dialog = await screen.findByRole("dialog", { name: "E-mails do cliente" });
    expect(within(dialog).getByRole("progressbar", { name: "Passo 3 de 3" })).toBeInTheDocument();
    await userEvent.type(within(dialog).getByLabelText("Novo e-mail"), "ana@souza.com.br");
    await userEvent.click(within(dialog).getByRole("button", { name: "Concluir" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    const later = writes(sent).slice(2);
    expect(later.map((r) => [r.method, r.path, r.body])).toEqual([
      [
        "PATCH",
        "/api/projects/p-1/content",
        { row_version: 3, description: "Casa de campo.", details: [{ key: "location", value: "Nova Lima" }] },
      ],
      ["PATCH", "/api/projects/p-1", { row_version: 4, recipients: ["ana@souza.com.br"] }],
    ]);
  });

  it("ask for no cover: a new project already has one", async () => {
    arrive();
    for (const name of ["Etapas", "Descrição e informações"]) {
      await userEvent.click(within(await screen.findByRole("dialog", { name })).getByRole("button", { name: "Pular" }));
    }
    const last = await screen.findByRole("dialog", { name: "E-mails do cliente" });
    expect(within(last).getByRole("progressbar", { name: "Passo 3 de 3" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Foto de capa" })).toBeNull();
  });

  it("stay open on a click outside, and say once finished that it can all change later", async () => {
    arrive();
    const dialog = await screen.findByRole("dialog", { name: "Etapas" });
    expect(within(dialog).getByText("Passo 1 de 3")).toBeInTheDocument(); // the title names the step
    await userEvent.click(document.body); // a stray click on the page behind
    expect(screen.getByRole("dialog", { name: "Etapas" })).toBeInTheDocument();
    for (const name of ["Etapas", "Descrição e informações", "E-mails do cliente"]) {
      const step = await screen.findByRole("dialog", { name });
      await userEvent.click(within(step).getByRole("button", { name: name === "E-mails do cliente" ? "Concluir" : "Pular" }));
    }
    expect(await screen.findByText(/Projeto configurado/)).toBeInTheDocument();
  });

  it("go on without saving when nothing was typed", async () => {
    const sent = arrive();
    await userEvent.click(within(await screen.findByRole("dialog", { name: "Etapas" })).getByRole("button", { name: "Pular" }));
    const details = await screen.findByRole("dialog", { name: "Descrição e informações" });
    await userEvent.click(within(details).getByRole("button", { name: "Continuar" }));
    const emails = await screen.findByRole("dialog", { name: "E-mails do cliente" });
    await userEvent.click(within(emails).getByRole("button", { name: "Concluir" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(writes(sent)).toEqual([]);
  });

  it("can be skipped step by step, changing nothing", async () => {
    const sent = arrive();
    for (const name of ["Etapas", "Descrição e informações", "E-mails do cliente"]) {
      const dialog = await screen.findByRole("dialog", { name });
      await userEvent.click(within(dialog).getByRole("button", { name: "Pular" }));
    }
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(writes(sent)).toEqual([]);
  });
});
