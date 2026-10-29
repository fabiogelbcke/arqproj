import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ClientApp } from "../client/ClientApp";
import { whatsappLink } from "../client/ProposalPhase";
import type { Page } from "../client/format";
import { fakeApi, ME, renderAt, TENANT } from "../test/render";
import { formatAmount, instalments, parseAmount, type Generator, type ProposalView } from "./proposals";

afterEach(() => vi.unstubAllGlobals());

describe("WhatsApp links", () => {
  it("use the office's WhatsApp number, a Brazilian one without its +55 too", () => {
    expect(whatsappLink("(47) 99123-4567", "(47) 3000-0000")).toBe("https://wa.me/5547991234567");
    expect(whatsappLink("+55 47 99123-4567", "")).toBe("https://wa.me/5547991234567");
    expect(whatsappLink("+1 415 555 0100", "")).toBe("https://wa.me/14155550100");
  });

  it("else use the phone, when it is a Brazilian mobile", () => {
    expect(whatsappLink("", "(47) 99123-4567")).toBe("https://wa.me/5547991234567");
    expect(whatsappLink("", "+55 47 99123-4567")).toBe("https://wa.me/5547991234567");
    expect(whatsappLink("", "(47) 3000-0000")).toBeNull(); // a landline
    expect(whatsappLink("", "+1 415 555 0100")).toBeNull();
  });
});

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
  whatsapp: "",
  email: "contato@alinea.example",
  pdf_url: "/api/pages/casa-jardim/proposal.pdf?v=2",
};

const PAGE: Page = {
  id: "6f1c1d1e-0000-4000-8000-0000000000b1",
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
    expect(screen.getByText("Para Helena Duarte")).toBeInTheDocument();
    // The summary first: the fee, how it is paid, what is included.
    const summary = screen.getAllByRole("definition").map((d) => d.textContent);
    expect(summary).toEqual(expect.arrayContaining(["R$ 29.000,00", "Parcela única", "1 serviço"]));
    const services = within(screen.getByRole("region", { name: "O que está incluído" }));
    expect(services.getByRole("heading", { name: "Briefing" })).toBeInTheDocument();
    expect(services.getByText("Projeto estrutural")).toBeInTheDocument(); // not included
    const fees = within(screen.getByRole("region", { name: "Honorários e pagamento" }));
    expect(fees.getByText("(vinte e nove mil reais)")).toBeInTheDocument();
    expect(fees.getByRole("listitem")).toHaveTextContent("Parcela 1no aceite da propostaR$ 14.500,00");
    // The PDF: beside the title, pinned on phones, and again at the end.
    const downloads = screen.getAllByRole("link", { name: "Baixar proposta em PDF" });
    expect(downloads).toHaveLength(3);
    for (const download of downloads)
      expect(download).toHaveAttribute("href", "/api/pages/casa-jardim/proposal.pdf?v=2&download=true");
    // Next steps: talk to the office. A landline: a call, no WhatsApp.
    const next = within(screen.getByRole("region", { name: "Próximos passos" }));
    expect(next.getByRole("link", { name: "Enviar e-mail" })).toHaveAttribute("href", "mailto:contato@alinea.example");
    expect(next.getByRole("link", { name: "Ligar · (47) 3000-0000" })).toHaveAttribute("href", "tel:4730000000");
    expect(next.queryByRole("link", { name: "WhatsApp" })).toBeNull();
    expect(next.getByText("Arq. Laura Mendes")).toBeInTheDocument();
    // No stages, files or email sign-up.
    expect(screen.queryByText(/Cronograma|Novidades por e-mail/)).toBeNull();
    expect(screen.queryByRole("navigation", { name: "Ferramentas do escritório" })).toBeNull();
  });

  it("offers WhatsApp for the office's WhatsApp number", async () => {
    client({ ...PAGE, proposal: { ...PROPOSAL, whatsapp: "(47) 99123-4567" } });
    expect(await screen.findByRole("link", { name: "WhatsApp" })).toHaveAttribute("href", "https://wa.me/5547991234567");
  });

  it("says the proposal is coming when none is saved yet", async () => {
    client({ ...PAGE, proposal: null, proposal_url: null });
    expect(await screen.findByText(/A proposta está sendo preparada/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Baixar proposta em PDF" })).toBeNull();
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
    whatsapp: "",
    email: "",
  },
  versions: [],
  presets: [
    { title: "Briefing", description: "Conversas." },
    { title: "Anteprojeto", description: "Planta humanizada." },
    { title: "Imagens renderizadas", description: "Perspectivas." },
  ],
  office: { address: "", city: "Joinville", phone: "", whatsapp: "", email: "", signatory: "Arq. Laura Mendes" },
  default_intro: "Abertura padrão.",
  default_notes: "Observações padrão.",
};

type Reply = { status?: number; body?: unknown };

/** Services start collapsed: "Editar" opens one. */
const editService = async (title: string) =>
  userEvent.click(await screen.findByRole("button", { name: `Editar ${title}` }));

function generator(extra: Record<string, (body: unknown) => Reply | Promise<Reply>> = {}) {
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
    await editService("Briefing");
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
    // The one added opens; the others stay a line each.
    expect(screen.getAllByLabelText(/^Nome do serviço/).map((f) => (f as HTMLInputElement).value)).toEqual([
      "Imagens renderizadas",
    ]);
    expect(screen.getAllByRole("listitem").map((item) => item.textContent)).toEqual([
      expect.stringContaining("1.Briefing"),
      expect.stringContaining("2.Anteprojeto"),
      expect.stringContaining("3.Imagens renderizadas"),
    ]);
  });

  it("asks before a link in the painel discards unsaved changes", async () => {
    const { router } = generator();
    const crumb = async () =>
      within(await screen.findByRole("navigation", { name: "Onde você está" })).getByRole("link", { name: "Projetos" });
    await userEvent.click(await crumb()); // nothing changed: leaves straight away
    await waitFor(() => expect(router.state.location.pathname).toBe("/"));
    await router.navigate("/projetos/p-1/proposta");

    await editService("Briefing");
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

  it("keeps what is typed while a save is under way", async () => {
    let finish = () => {};
    const versions: unknown[] = [];
    const { router } = generator({
      "GET /api/projects/p-1/proposal": () => ({ body: { ...GENERATOR, versions } }),
      "POST /api/projects/p-1/proposals": () =>
        new Promise((resolve) => {
          finish = () => {
            const saved = { version: 1, created_at: "2026-10-28T12:00:00Z", created_by: "Ana" };
            versions.unshift(saved);
            resolve({ status: 201, body: saved });
          };
        }),
    });
    await userEvent.type(await screen.findByLabelText(/Valor total/), "1.000,00");
    await userEvent.click(screen.getByRole("button", { name: "Salvar proposta" }));
    await editService("Briefing");
    const description = () => screen.getAllByLabelText("Descrição")[0] as HTMLTextAreaElement;
    await userEvent.type(description(), " E visitas.");
    finish();
    expect(await screen.findByText(/Versão 1/)).toBeInTheDocument(); // reloaded with the saved version
    expect(description().value).toBe("Conversas. E visitas.");

    // Still unsaved: leaving asks.
    await userEvent.click(within(screen.getByRole("navigation", { name: "Onde você está" })).getByRole("link", { name: "Projetos" }));
    expect(await screen.findByRole("alertdialog")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/projetos/p-1/proposta");
  });

  it("keeps the draft when reloading the proposal's details fails", async () => {
    let loads = 0;
    generator({
      "GET /api/projects/p-1/proposal": () => (++loads === 1 ? { body: GENERATOR } : { status: 500, body: {} }),
      "PUT /api/proposal-presets": (body) => ({ body: (body as { services: unknown }).services }),
    });
    const description = async () => (await screen.findAllByLabelText("Descrição"))[0] as HTMLTextAreaElement;
    await editService("Briefing");
    await userEvent.type(await description(), " E visitas.");
    await userEvent.type(screen.getByLabelText("Nome do cliente"), " Souza");
    await userEvent.click(screen.getByRole("button", { name: "Salvar como padrão deste serviço" }));
    await waitFor(() => expect(loads).toBe(3), { timeout: 4000 }); // the reload and its retry both fail
    await new Promise((settle) => setTimeout(settle, 50));
    expect((screen.getByLabelText("Nome do cliente") as HTMLInputElement).value).toBe("Helena Duarte Souza");
    expect((await description()).value).toBe("Conversas. E visitas.");
  });

  it("removes a service with a way to undo it, and leaves it out when saving", async () => {
    const sent = generator({
      "POST /api/projects/p-1/proposals": () => ({
        status: 201,
        body: { version: 1, created_at: "2026-10-28T12:00:00Z", created_by: "Ana" },
      }),
    });
    await userEvent.click(await screen.findByRole("button", { name: "Remover Briefing" }));
    expect(screen.getByText("“Briefing” removido desta proposta.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Editar Anteprojeto" }).closest("li")).toHaveTextContent("1.Anteprojeto");
    await userEvent.click(screen.getByRole("button", { name: "Desfazer" }));
    expect(screen.getByRole("button", { name: "Editar Briefing" }).closest("li")).toHaveTextContent("1.Briefing");

    await userEvent.click(screen.getByRole("button", { name: "Remover Briefing" }));
    await userEvent.type(screen.getByLabelText(/Valor total/), "1.000,00");
    await userEvent.click(screen.getByRole("button", { name: "Salvar proposta" }));
    await waitFor(() => expect(sent.some((r) => r.path.endsWith("/proposals"))).toBe(true));
    const body = sent.find((r) => r.path.endsWith("/proposals"))!.body as { services: unknown[] };
    expect(body.services).toEqual([{ title: "Anteprojeto", description: expect.any(String) }]);
  });

  it("moves a service past one removed", async () => {
    generator();
    await userEvent.click(await screen.findByRole("button", { name: "Adicionar serviço" }));
    await userEvent.click(within(await screen.findByRole("menu")).getByRole("menuitem", { name: "Imagens renderizadas" }));
    await userEvent.click(screen.getByRole("button", { name: "Remover Anteprojeto" }));
    await userEvent.click(screen.getByRole("button", { name: "Mover Imagens renderizadas para cima" }));
    // The one added is open: its button says "Concluir".
    expect(screen.getByRole("button", { name: "Concluir Imagens renderizadas" }).closest("li")).toHaveTextContent(
      "1.Imagens renderizadas",
    );
  });

  it("opens an unnamed service when saving asks for its name", async () => {
    generator();
    await userEvent.click(await screen.findByRole("button", { name: "Adicionar serviço" }));
    await userEvent.click(within(await screen.findByRole("menu")).getByRole("menuitem", { name: "Serviço em branco" }));
    await userEvent.click(screen.getByRole("button", { name: "Concluir Serviço sem nome" }));
    expect(screen.queryByLabelText(/^Nome do serviço/)).toBeNull();
    await userEvent.type(screen.getByLabelText(/Valor total/), "1.000,00");
    await userEvent.click(screen.getByRole("button", { name: "Salvar proposta" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByLabelText(/^Nome do serviço/)).toHaveValue("");
  });

  it("asks an owner whether a changed office detail updates the office", async () => {
    const sent = generator({
      "POST /api/projects/p-1/proposals": () => ({
        status: 201,
        body: { version: 1, created_at: "2026-10-28T12:00:00Z", created_by: "Ana" },
      }),
    });
    await userEvent.type(await screen.findByLabelText(/Valor total/), "1.000,00");
    const signatory = screen.getByLabelText(/^Quem assina/);
    await userEvent.clear(signatory);
    await userEvent.type(signatory, "Arq. Bruno Lima");
    await userEvent.click(screen.getByRole("button", { name: "Salvar proposta" }));
    const ask = await screen.findByRole("alertdialog");
    expect(ask).toHaveTextContent("diferentes dos salvos no escritório: Quem assina.");
    expect(sent.some((r) => r.path.endsWith("/proposals"))).toBe(false); // nothing saved until answered
    await userEvent.keyboard("{Escape}"); // neither: back to the form, unsaved
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    expect(sent.some((r) => r.path.endsWith("/proposals"))).toBe(false);

    await userEvent.click(screen.getByRole("button", { name: "Salvar proposta" }));
    await userEvent.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Atualizar escritório" }));
    await waitFor(() => expect(sent.some((r) => r.path.endsWith("/proposals"))).toBe(true));
    expect(sent.find((r) => r.path.endsWith("/proposals"))!.query).toBe("?update_office=true");
  });

  it("saves only the proposal when the owner keeps the office's details", async () => {
    const sent = generator({
      "POST /api/projects/p-1/proposals": () => ({
        status: 201,
        body: { version: 1, created_at: "2026-10-28T12:00:00Z", created_by: "Ana" },
      }),
    });
    await userEvent.type(await screen.findByLabelText(/Valor total/), "1.000,00");
    await userEvent.type(screen.getByLabelText(/^Quem assina/), " Lima");
    await userEvent.click(screen.getByRole("button", { name: "Salvar proposta" }));
    await userEvent.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Só nesta proposta" }));
    await waitFor(() => expect(sent.some((r) => r.path.endsWith("/proposals"))).toBe(true));
    expect(sent.find((r) => r.path.endsWith("/proposals"))!.query).toBe("?update_office=false");
  });

  it("doesn't ask a member", async () => {
    const sent = generator({
      "GET /api/me": () => ({ body: { ...ME, role: "member" } }),
      "POST /api/projects/p-1/proposals": () => ({
        status: 201,
        body: { version: 1, created_at: "2026-10-28T12:00:00Z", created_by: "Ana" },
      }),
    });
    await userEvent.type(await screen.findByLabelText(/Valor total/), "1.000,00");
    await userEvent.type(screen.getByLabelText(/^Quem assina/), " Lima");
    await userEvent.click(screen.getByRole("button", { name: "Salvar proposta" }));
    await waitFor(() => expect(sent.some((r) => r.path.endsWith("/proposals"))).toBe(true));
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("doesn't ask an owner about details the office lacks: those are filled in", async () => {
    const sent = generator({
      "POST /api/projects/p-1/proposals": () => ({
        status: 201,
        body: { version: 1, created_at: "2026-10-28T12:00:00Z", created_by: "Ana" },
      }),
    });
    await userEvent.type(await screen.findByLabelText(/Valor total/), "1.000,00");
    await userEvent.type(screen.getByLabelText(/^Endereço/), "Rua das Palmeiras, 120");
    await userEvent.click(screen.getByRole("button", { name: "Salvar proposta" }));
    await waitFor(() => expect(sent.some((r) => r.path.endsWith("/proposals"))).toBe(true));
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("marks the proposal accepted only after asking", async () => {
    const sent = generator({ "POST /api/projects/p-1/accept-proposal": () => ({ body: {} }) });
    await userEvent.click(await screen.findByRole("button", { name: "Proposta aceita" }));
    await userEvent.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Marcar como aceita" }));
    await waitFor(() => expect(sent.some((r) => r.path.endsWith("accept-proposal"))).toBe(true));
    expect(sent.find((r) => r.path.endsWith("accept-proposal"))!.body).toEqual({ row_version: 3 });
  });
});
