import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fakeApi, ME, TENANT } from "../test/render";
import { ClientApp } from "./ClientApp";
import type { Page } from "./format";
import { SharePage } from "./SharePage";
import { shareToken } from "./shareToken";

const PAGE: Page = {
  office: { name: "Alinea", logo_url: null, logo_dark_url: null },
  locale: "pt-BR",
  timezone: "America/Sao_Paulo",
  name: "Casa Jardim",
  client_name: "Família Oliveira",
  project_type: "Projeto Arquitetônico",
  project_type_key: "architecture",
  description: "",
  cover_url: null,
  completed: false,
  current_position: null,
  last_update: "2026-10-15T23:30:00Z",
  details: [],
  stages: [
    { position: 1, title: "Briefing", about: null, notes: "", completed: true },
    { position: 2, title: "Levantamento", about: null, notes: "", completed: false },
  ],
  next_meeting: null,
};

const file = (key: string, name: string, size: number) => ({
  key,
  name,
  kind: "pdf",
  size,
  modified_at: "2026-10-10T12:00:00Z",
  older: [],
});
const FILES = {
  stages: [
    { position: 1, groups: [{ folder: null, files: [file("k1", "Programa.pdf", 1024)] }] },
    {
      position: 2,
      groups: [{ folder: null, files: [file("k2", "Planta.pdf", 2048), file("k3", "Corte.pdf", 4096)] }],
    },
  ],
  updates: [],
};
const LINK = {
  id: "l1",
  label: "Marcenaria Silva",
  made_by: null,
  created_at: "2026-10-25T12:00:00Z",
  expires_at: "2026-11-24T12:00:00Z",
  disabled: false,
  expired: false,
  files: 2,
  available: 2,
  newer: 1,
  downloads: 3,
  last_download_at: null,
};

function at(handlers: Record<string, (body: unknown) => { status?: number; body?: unknown }>) {
  window.history.pushState({}, "", "/casa-jardim");
  const sent = fakeApi({
    "GET /api/tenant": () => ({ body: TENANT }),
    "GET /api/pages/casa-jardim": () => ({ body: PAGE }),
    "GET /api/pages/casa-jardim/files": () => ({ body: FILES }),
    ...handlers,
  });
  render(<ClientApp />);
  return sent;
}

beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

describe("sharing files by link", () => {
  it("shares a stage's files: they start ticked, and the link is kept on this device", async () => {
    const sent = at({
      "POST /api/pages/casa-jardim/shares": () => ({
        status: 201,
        body: { link: { ...LINK, newer: 0, downloads: 0 }, url: "http://alinea.localhost/share/tok", owner: "own-1" },
      }),
    });
    await userEvent.click(await screen.findByRole("button", { name: "Compartilhar arquivos de Levantamento" }));
    const dialog = await screen.findByRole("dialog", { name: "Compartilhar arquivos" });
    expect(within(dialog).getByRole("checkbox", { name: /Planta\.pdf/ })).toBeChecked();
    expect(within(dialog).getByRole("checkbox", { name: /Corte\.pdf/ })).toBeChecked();
    expect(within(dialog).queryByRole("checkbox", { name: /Programa\.pdf/ })).toBeNull(); // only this stage's
    expect(within(dialog).getByText(/^Escolha os arquivos de 02 Levantamento/)).toBeInTheDocument();
    expect(within(dialog).getByLabelText("Para quem?")).toHaveAttribute("placeholder", "Ex.: Marcenaria Silva");
    expect(within(dialog).getByRole("checkbox", { name: "Selecionar todos os arquivos de 02 Levantamento" })).toBeChecked();
    expect(within(dialog).getByRole("status")).toHaveTextContent("2 arquivos · 6 KB");
    await userEvent.click(within(dialog).getByRole("checkbox", { name: /Corte\.pdf/ }));
    await userEvent.type(within(dialog).getByLabelText("Para quem?"), "Marcenaria Silva");
    await userEvent.click(within(dialog).getByRole("radio", { name: "7 dias" }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Gerar link" }));
    const ready = await screen.findByRole("dialog", { name: "Link pronto" });
    expect(within(ready).getByLabelText("Link para compartilhar")).toHaveValue("http://alinea.localhost/share/tok");
    expect(sent.find((r) => r.method === "POST" && r.path.endsWith("/shares"))?.body).toEqual({
      files: ["k2"],
      label: "Marcenaria Silva",
      expiry: "7d",
    });
    expect(JSON.parse(localStorage.getItem("shares:casa-jardim")!)).toEqual([
      { id: "l1", owner: "own-1", url: "http://alinea.localhost/share/tok" },
    ]);
    const clipboard = { writeText: vi.fn(async () => undefined) };
    vi.stubGlobal("navigator", { ...navigator, clipboard });
    await userEvent.click(within(ready).getByRole("button", { name: "Copiar link" }));
    expect(clipboard.writeText).toHaveBeenCalledWith("http://alinea.localhost/share/tok");
  });

  it("from the toolbar, shares whole stages or files picked one by one", async () => {
    const sent = at({
      "POST /api/pages/casa-jardim/shares": () => ({
        status: 201,
        body: { link: LINK, url: "http://alinea.localhost/share/tok", owner: "own-1" },
      }),
    });
    await userEvent.click(await screen.findByRole("button", { name: "Compartilhar arquivos" }));
    const dialog = await screen.findByRole("dialog", { name: "Compartilhar arquivos" });
    // Whole stages first: each stage a checkbox, no files listed.
    expect(within(dialog).queryByRole("checkbox", { name: /Planta\.pdf/ })).toBeNull();
    await userEvent.click(within(dialog).getByRole("checkbox", { name: /02 Levantamento/ }));
    expect(within(dialog).getByRole("status")).toHaveTextContent("2 arquivos · 6 KB");
    // Picking files: a stage opens to its files, its checkbox in its row.
    await userEvent.click(within(dialog).getByRole("radio", { name: "Escolher arquivos" }));
    expect(within(dialog).getByRole("status")).toHaveTextContent("Nenhum arquivo selecionado");
    await userEvent.click(within(dialog).getByRole("button", { name: /02 Levantamento/ }));
    await userEvent.click(within(dialog).getByRole("checkbox", { name: /Corte\.pdf/ }));
    const stage = within(dialog).getByRole("checkbox", { name: "Selecionar todos os arquivos de 02 Levantamento" });
    expect(stage).toBePartiallyChecked();
    await userEvent.click(within(dialog).getByRole("button", { name: "Gerar link" }));
    await screen.findByRole("dialog", { name: "Link pronto" });
    expect(sent.find((r) => r.method === "POST" && r.path.endsWith("/shares"))?.body).toMatchObject({ files: ["k3"] });
  });

  it("opens above the stages with nothing ticked, and refuses more than 300 MB", async () => {
    const big = { ...FILES, stages: [{ position: 1, groups: [{ folder: null, files: [file("k9", "Maquete.zip", 301 * 1024 * 1024)] }] }] };
    at({ "GET /api/pages/casa-jardim/files": () => ({ body: big }) });
    await userEvent.click(await screen.findByRole("button", { name: "Compartilhar arquivos" }));
    const dialog = await screen.findByRole("dialog", { name: "Compartilhar arquivos" });
    const make = within(dialog).getByRole("button", { name: "Gerar link" });
    expect(make).toBeDisabled();
    expect(within(dialog).getByRole("status")).toHaveTextContent("Nenhum arquivo selecionado");
    await userEvent.click(within(dialog).getByRole("checkbox", { name: /01 Briefing/ }));
    expect(within(dialog).getByText(/O limite é de 300 MB por link/)).toBeInTheDocument();
    expect(make).toBeDisabled();
  });

  it("lists this device's links, updates one to newer versions and turns one off", async () => {
    localStorage.setItem("shares:casa-jardim", JSON.stringify([{ id: "l1", owner: "own-1", url: "http://x/share/tok" }]));
    const sent = at({
      "POST /api/pages/casa-jardim/shares/mine": () => ({ body: [LINK] }),
      "POST /api/pages/casa-jardim/shares/l1/refresh": () => ({ body: { ...LINK, newer: 0 } }),
      "POST /api/pages/casa-jardim/shares/l1/disable": () => ({ body: { ...LINK, newer: 0, disabled: true } }),
    });
    await userEvent.click(await screen.findByRole("button", { name: "Compartilhar arquivos" }));
    // Making a link first; the links made have their own tab.
    expect(await screen.findByRole("tab", { name: "Novo link" })).toHaveAttribute("aria-selected", "true");
    expect(screen.queryByRole("region", { name: "Links criados neste dispositivo" })).toBeNull();
    await userEvent.click(screen.getByRole("tab", { name: "Links criados (1)" }));
    const links = await screen.findByRole("region", { name: "Links criados neste dispositivo" });
    expect(sent.find((r) => r.path.endsWith("/shares/mine"))?.body).toEqual({ owners: ["own-1"] });
    expect(within(links).getByText("Marcenaria Silva")).toBeInTheDocument();
    expect(within(links).getByText(/2 de 2 arquivos disponíveis · 3 downloads/)).toBeInTheDocument();
    expect(within(links).getByText("1 arquivo tem versão mais recente")).toBeInTheDocument();
    await userEvent.click(within(links).getByRole("button", { name: "Atualizar link" }));
    await waitFor(() => expect(within(links).queryByText("1 arquivo tem versão mais recente")).toBeNull());
    expect(sent.find((r) => r.path.endsWith("/refresh"))?.body).toEqual({ owner: "own-1" });
    await userEvent.click(within(links).getByRole("button", { name: "Desativar" }));
    const confirm = await screen.findByRole("alertdialog", { name: "Desativar este link?" });
    await userEvent.click(within(confirm).getByRole("button", { name: "Desativar" }));
    expect(await within(links).findByText("Desativado")).toBeInTheDocument();
    expect(sent.find((r) => r.path.endsWith("/disable"))?.body).toEqual({ owner: "own-1" });
  });

  it("keeps the links reachable when no file can be picked, to turn them off", async () => {
    localStorage.setItem("shares:casa-jardim", JSON.stringify([{ id: "l1", owner: "own-1", url: "http://x/share/tok" }]));
    at({
      "GET /api/pages/casa-jardim/files": () => ({ body: { stages: [], updates: [] } }),
      "POST /api/pages/casa-jardim/shares/mine": () => ({ body: [{ ...LINK, available: 0 }] }),
    });
    await userEvent.click(await screen.findByRole("button", { name: "Compartilhar arquivos" }));
    const dialog = await screen.findByRole("dialog", { name: "Compartilhar arquivos" });
    // Nothing to pick: it opens on the links, to turn one off.
    const links = await within(dialog).findByRole("region", { name: "Links criados neste dispositivo" });
    expect(within(links).getByRole("button", { name: "Desativar" })).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("tab", { name: "Novo link" }));
    expect(within(dialog).getByText("Ainda não há arquivos para compartilhar.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Compartilhar arquivos de / })).toBeNull(); // no stage has files
  });

  it("shows staff every link of the project, and who made each", async () => {
    window.history.pushState({}, "", "/casa-jardim");
    fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/me": () => ({ body: { ...ME, page_tour_seen: true } }),
      "GET /api/pages/casa-jardim": () => ({
        body: { ...PAGE, staff: { project_id: "p1", status: "active", row_version: 1, recipients: [] } },
      }),
      "GET /api/pages/casa-jardim/files": () => ({ body: FILES }),
      "GET /api/pages/casa-jardim/shares": () => ({
        body: [LINK, { ...LINK, id: "l2", label: null, made_by: "Ana", newer: 0, available: 1, downloads: 0 }],
      }),
    });
    render(<ClientApp />);
    await userEvent.click(await screen.findByRole("button", { name: "Compartilhar arquivos" }));
    await userEvent.click(await screen.findByRole("tab", { name: "Links criados (2)" }));
    const links = await screen.findByRole("region", { name: "Links deste projeto" });
    expect(within(links).getByText(/^Cliente · 2 de 2/)).toBeInTheDocument();
    expect(within(links).getByText("Link sem destinatário")).toBeInTheDocument();
    // Portuguese counts 0 as singular: no download reads as none, not as one.
    expect(within(links).getByText(/^Ana · 1 de 2 arquivos disponíveis · Nenhum download$/)).toBeInTheDocument();
    expect(within(links).getByText(/^Ana · 1 de 2/)).toBeInTheDocument();
  });
});

describe("the supplier's page", () => {
  it("reads the token from its address only", () => {
    expect(shareToken("/share/AbC-12_x")).toBe("AbC-12_x");
    expect(shareToken("/share/")).toBeNull();
    expect(shareToken("/casa-jardim")).toBeNull();
  });

  it("lists the files to download, and says how many are no longer available", async () => {
    fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/share/tok": () => ({
        body: {
          office: PAGE.office,
          locale: "pt-BR",
          timezone: "America/Sao_Paulo",
          project: "Casa Jardim",
          label: "Marcenaria Silva",
          expires_at: "2026-11-24T12:00:00Z",
          files: [{ key: "s1", name: "Planta v2.pdf", kind: "pdf", size: 2048, modified_at: "2026-10-10T12:00:00Z", stage: "02 Levantamento" }],
          unavailable: 2,
        },
      }),
    });
    render(<SharePage token="tok" />);
    expect(await screen.findByRole("heading", { name: "Arquivos compartilhados" })).toBeInTheDocument();
    expect(screen.getByText("Arquivos do projeto Casa Jardim, compartilhados por Alinea.")).toBeInTheDocument();
    expect(screen.getByText("Para: Marcenaria Silva · Disponível até 24/11/2026")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Baixar Planta v2.pdf" })).toHaveAttribute("href", "/api/share/tok/files/s1");
    expect(screen.getByText("2 arquivos compartilhados não estão mais disponíveis.")).toBeInTheDocument();
  });

  it("says when a link no longer works", async () => {
    fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/share/tok": () => ({ status: 404, body: { error: "share_not_found" } }),
    });
    render(<SharePage token="tok" />);
    expect(await screen.findByRole("heading", { name: "Link indisponível" })).toBeInTheDocument();
    expect(screen.getByText(/Peça um novo a quem o enviou/)).toBeInTheDocument();
  });
});
