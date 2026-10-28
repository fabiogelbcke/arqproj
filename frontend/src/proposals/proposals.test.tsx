import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ClientApp } from "../client/ClientApp";
import type { Page } from "../client/format";
import { fakeApi, ME, renderAt, TENANT } from "../test/render";
import { formatAmount, instalments, parseAmount, type Generator, type ProposalView } from "./proposals";

afterEach(() => vi.unstubAllGlobals());

describe("amounts as typed", () => {
  it.each([
    ["29.000,00", 2_900_000],
    ["29000", 2_900_000],
    ["R$ 29.000,50", 2_900_050],
    ["1.234.567,8", 123_456_780],
    ["0,05", 5],
    ["29.000", 2_900_000], // a thousands mark, not centavos
  ])("reads %j in Portuguese", (typed, centavos) => {
    expect(parseAmount(typed, "pt-BR")).toBe(centavos);
  });

  it("reads English amounts", () => {
    expect(parseAmount("29,000.50", "en")).toBe(2_900_050);
  });

  it.each(["", "abc", "R$", "12345678901"])("refuses %j", (typed) => {
    expect(parseAmount(typed, "pt-BR")).toBeNull();
  });

  it("shows centavos as the field writes them", () => {
    expect(formatAmount(2_900_000, "pt-BR")).toBe("29.000,00");
    expect(formatAmount(2_900_000, "en")).toBe("29,000.00");
  });

  it("splits a fee into equal instalments that add up to it", () => {
    expect(instalments(2_900_000, 5)).toEqual([580_000, 580_000, 580_000, 580_000, 580_000]);
    const uneven = instalments(1_000_000, 3);
    expect(uneven).toEqual([333_334, 333_333, 333_333]);
    expect(uneven.reduce((a, b) => a + b)).toBe(1_000_000);
  });
});

const PROPOSAL: ProposalView = {
  version: 2,
  date_line: "Joinville, 28 de outubro de 2026",
  client_name: "Helena Duarte",
  intro: "Conforme solicitação, segue nossa proposta.",
  services: [{ title: "Briefing", description: "Conversas sobre o programa." }],
  fee: "R$ 29.000,00",
  fee_in_words: "vinte e nove mil reais",
  payments: [{ amount: "R$ 14.500,00", when: "no aceite da proposta" }],
  not_included: ["Projeto estrutural"],
  notes: "As despesas com RRT correm por conta do contratante.",
  signatory: "Arq. Laura Mendes",
  address: "Rua das Palmeiras, 120",
  phone: "(47) 3000-0000",
  email: "contato@alinea.example",
  pdf_url: "/api/pages/casa-jardim/proposal.pdf?v=2",
};

const PAGE: Page = {
  office: { name: "Alinea", logo_url: null, logo_dark_url: null },
  locale: "pt-BR",
  timezone: "America/Sao_Paulo",
  name: "Casa Jardim",
  client_name: "Helena Duarte",
  project_type: "",
  project_type_key: "architecture",
  description: "",
  cover_url: null,
  completed: false,
  current_position: null,
  last_update: "2026-10-15T23:30:00Z",
  details: [],
  stages: [],
  next_meeting: null,
  in_proposal: true,
  proposal: PROPOSAL,
  proposal_url: PROPOSAL.pdf_url,
};

function client(page: Page, extra: Record<string, (body: unknown) => { status?: number; body?: unknown }> = {}) {
  window.history.pushState({}, "", "/casa-jardim");
  const sent = fakeApi({
    "GET /api/tenant": () => ({ body: TENANT }),
    "GET /api/pages/casa-jardim": () => ({ body: page }),
    ...extra,
  });
  render(<ClientApp />);
  return sent;
}

describe("a project's page while it is a proposal", () => {
  it("shows the proposal, its PDF and the office's contact, and nothing of the work", async () => {
    client(PAGE);
    expect(await screen.findByRole("heading", { level: 1, name: "Casa Jardim" })).toBeInTheDocument();
    expect(screen.getByText("1. BRIEFING")).toBeInTheDocument();
    expect(
      screen.getByText("Os honorários para a elaboração dos trabalhos serão de R$ 29.000,00 (vinte e nove mil reais)."),
    ).toBeInTheDocument();
    expect(screen.getByText("R$ 14.500,00 no aceite da proposta")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Baixar PDF" })).toHaveAttribute(
      "href",
      "/api/pages/casa-jardim/proposal.pdf?v=2&download=true",
    );
    expect(screen.getByRole("link", { name: "contato@alinea.example" })).toHaveAttribute(
      "href",
      "mailto:contato@alinea.example",
    );
    expect(screen.getByRole("link", { name: "(47) 3000-0000" })).toHaveAttribute("href", "tel:4730000000");
    // No stages, files or email sign-up.
    expect(screen.queryByText(/Cronograma|Novidades por e-mail/)).toBeNull();
    expect(screen.queryByRole("navigation", { name: "Ferramentas do escritório" })).toBeNull();
  });

  it("says the proposal is coming when none is saved yet", async () => {
    client({ ...PAGE, proposal: null, proposal_url: null });
    expect(await screen.findByText(/A proposta está sendo preparada/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Baixar PDF" })).toBeNull();
  });

  it("lets staff change the proposal or mark it accepted, after asking", async () => {
    const staffPage = { ...PAGE, staff: { project_id: "p-1", status: "proposal" as const, row_version: 7, recipients: [] } };
    let accepted = false;
    const sent = client(staffPage, {
      "GET /api/me": () => ({ body: ME }),
      "POST /api/projects/p-1/accept-proposal": () => {
        accepted = true;
        return { body: {} };
      },
    });
    const bar = await screen.findByRole("navigation", { name: "Ferramentas do escritório" });
    expect(within(bar).getByRole("link", { name: "Editar proposta" })).toHaveAttribute(
      "href",
      "/painel/projetos/p-1/proposta",
    );
    const accept = within(bar).getByRole("button", { name: "Proposta aceita" });
    await waitFor(() => expect(accept).toBeEnabled());
    await userEvent.click(accept);
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent("Nenhum e-mail é enviado.");
    expect(accepted).toBe(false);
    await userEvent.click(within(dialog).getByRole("button", { name: "Marcar como aceita" }));
    await waitFor(() => expect(accepted).toBe(true));
    expect(sent.find((r) => r.path.endsWith("accept-proposal"))!.body).toEqual({ row_version: 7 });
  });
});

describe("an accepted proposal", () => {
  it("stays a link among the project's details", async () => {
    client({ ...PAGE, in_proposal: false, proposal: null, project_type: "Projeto Arquitetônico" });
    const link = await screen.findByRole("link", { name: "Ver proposta" });
    expect(link).toHaveAttribute("href", PROPOSAL.pdf_url);
  });
});

const GENERATOR: Generator = {
  project_id: "p-1",
  project_name: "Casa Jardim",
  slug: "casa-jardim",
  status: "proposal",
  row_version: 3,
  start: {
    client_name: "Helena Duarte",
    city: "Joinville",
    date: "2026-10-28",
    intro: "Abertura padrão.",
    services: [
      { title: "Briefing", description: "Conversas." },
      { title: "Anteprojeto", description: "Planta humanizada." },
    ],
    fee: null,
    payments: [],
    not_included: [],
    notes: "Observações padrão.",
    signatory: "Arq. Laura Mendes",
    address: "",
    phone: "",
    email: "",
  },
  versions: [],
  presets: [
    { title: "Briefing", description: "Conversas." },
    { title: "Anteprojeto", description: "Planta humanizada." },
    { title: "Imagens renderizadas", description: "Perspectivas." },
  ],
  office: { address: "", city: "Joinville", phone: "", email: "", signatory: "Arq. Laura Mendes" },
  default_intro: "Abertura padrão.",
  default_notes: "Observações padrão.",
};

function generator(extra: Record<string, (body: unknown) => { status?: number; body?: unknown }> = {}) {
  const sent = fakeApi({
    "GET /api/tenant": () => ({ body: TENANT }),
    "GET /api/me": () => ({ body: ME }),
    "GET /api/office": () => ({ body: { name: "Alinea", logo_url: null } }),
    "GET /api/projects/p-1/proposal": () => ({ body: GENERATOR }),
    "POST /api/projects/p-1/proposal/preview-page": () => ({ body: { ...PROPOSAL, fee: "", fee_in_words: "" } }),
    ...extra,
  });
  const router = renderAt("/projetos/p-1/proposta");
  return Object.assign(sent, { router });
}

describe("the proposal generator", () => {
  it("asks for the fee before saving, then saves amounts in centavos", async () => {
    const sent = generator({
      "POST /api/projects/p-1/proposals": () => ({
        status: 201,
        body: { version: 1, created_at: "2026-10-28T12:00:00Z", created_by: "Ana" },
      }),
    });
    const save = await screen.findByRole("button", { name: "Salvar proposta" });
    await userEvent.click(save);
    expect(await screen.findByRole("alert")).toHaveTextContent("Informe o valor dos honorários.");
    expect(sent.some((r) => r.path.endsWith("/proposals"))).toBe(false);

    await userEvent.type(screen.getByLabelText(/Valor total/), "29.000,00");
    await userEvent.clear(screen.getByLabelText("Número de parcelas"));
    await userEvent.type(screen.getByLabelText("Número de parcelas"), "2");
    await userEvent.click(screen.getByRole("button", { name: "Aplicar" }));
    expect(screen.getAllByLabelText(/^Quando/).map((field) => (field as HTMLInputElement).value)).toEqual([
      "no aceite da proposta",
      "30 dias após",
    ]);
    await userEvent.click(save);
    await waitFor(() => expect(sent.some((r) => r.path.endsWith("/proposals"))).toBe(true));
    const body = sent.find((r) => r.path.endsWith("/proposals"))!.body as Record<string, unknown>;
    expect(body.fee).toBe(2_900_000);
    expect(body.payments).toEqual([
      { amount: 1_450_000, when: "no aceite da proposta" },
      { amount: 1_450_000, when: "30 dias após" },
    ]);
    expect((body.services as unknown[]).length).toBe(2);
  });

  it("warns when the instalments don't add up to the fee", async () => {
    generator();
    await userEvent.type(await screen.findByLabelText(/Valor total/), "1.000,00");
    await userEvent.click(screen.getByRole("button", { name: "+ Adicionar parcela" }));
    await userEvent.type(screen.getByLabelText(/^Valor \(R\$\)/), "300,00");
    expect(await screen.findByRole("note")).toHaveTextContent("As parcelas somam R$ 300,00, e os honorários são R$ 1.000,00.");
  });

  it("saves an edited service as the office's default, keeping the others", async () => {
    const sent = generator({ "PUT /api/proposal-presets": (body) => ({ body: (body as { services: unknown }).services }) });
    const descriptions = await screen.findAllByLabelText("Descrição");
    await userEvent.type(descriptions[0]!, " E visitas.");
    await userEvent.click(screen.getByRole("button", { name: "Salvar como padrão deste serviço" }));
    await waitFor(() => expect(sent.some((r) => r.path === "/api/proposal-presets")).toBe(true));
    const services = (sent.find((r) => r.path === "/api/proposal-presets")!.body as { services: { title: string; description: string }[] })
      .services;
    expect(services.map((s) => s.title)).toEqual(["Briefing", "Anteprojeto", "Imagens renderizadas"]);
    expect(services[0]!.description).toBe("Conversas. E visitas.");
  });

  it("adds a service from the office's list, or a blank one", async () => {
    generator();
    await userEvent.click(await screen.findByRole("button", { name: "Adicionar serviço" }));
    const menu = await screen.findByRole("menu");
    // Services already in the proposal aren't offered again.
    expect(within(menu).queryByRole("menuitem", { name: "Briefing" })).toBeNull();
    await userEvent.click(within(menu).getByRole("menuitem", { name: "Imagens renderizadas" }));
    expect(screen.getAllByLabelText(/^Nome do serviço/).map((f) => (f as HTMLInputElement).value)).toEqual([
      "Briefing",
      "Anteprojeto",
      "Imagens renderizadas",
    ]);
  });

  it("asks before a link in the painel discards unsaved changes", async () => {
    const { router } = generator();
    const crumb = async () =>
      within(await screen.findByRole("navigation", { name: "Onde você está" })).getByRole("link", { name: "Projetos" });
    await userEvent.click(await crumb()); // nothing changed: leaves straight away
    await waitFor(() => expect(router.state.location.pathname).toBe("/"));
    await router.navigate("/projetos/p-1/proposta");

    await userEvent.type((await screen.findAllByLabelText("Descrição"))[0]!, " E visitas.");
    await userEvent.click(await crumb());
    const ask = await screen.findByRole("alertdialog");
    await userEvent.click(within(ask).getByRole("button", { name: "Continuar editando" }));
    expect(router.state.location.pathname).toBe("/projetos/p-1/proposta");
    expect((screen.getAllByLabelText("Descrição")[0] as HTMLTextAreaElement).value).toBe("Conversas. E visitas.");

    await userEvent.click(await crumb());
    await userEvent.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Sair sem salvar" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/"));
  });

  it("marks the proposal accepted only after asking", async () => {
    const sent = generator({ "POST /api/projects/p-1/accept-proposal": () => ({ body: {} }) });
    await userEvent.click(await screen.findByRole("button", { name: "Proposta aceita" }));
    await userEvent.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Marcar como aceita" }));
    await waitFor(() => expect(sent.some((r) => r.path.endsWith("accept-proposal"))).toBe(true));
    expect(sent.find((r) => r.path.endsWith("accept-proposal"))!.body).toEqual({ row_version: 3 });
  });
});
