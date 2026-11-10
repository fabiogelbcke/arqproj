import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, ME, renderAt, TENANT } from "../test/render";
import { moved, parsedArea, sendVideo, videoPoster, type Entry, type Portfolio } from "./portfolio";

// A browser decodes the video for its poster and sends it to Drive: neither
// happens in the test's document, so both are stood in for.
vi.mock("./portfolio", async (original) => ({
  ...(await original<typeof import("./portfolio")>()),
  videoPoster: vi.fn(),
  sendVideo: vi.fn(),
  resized: vi.fn((blob: Blob, name: string) => Promise.resolve(new File([blob], name, { type: "image/jpeg" }))),
}));
URL.createObjectURL ??= () => "blob:preview";
URL.revokeObjectURL ??= () => undefined;

afterEach(() => {
  vi.unstubAllGlobals();
  vi.mocked(videoPoster).mockReset();
  vi.mocked(sendVideo).mockReset();
});

const WITH_PORTFOLIO = { ...ME, features: ["portfolio"] };
// Before-and-after comparisons switched on too (A40, A46).
const COMPARING = { "GET /api/me": () => ({ body: { ...ME, features: ["portfolio", "before_after"] } }) };

function entry(changes: Partial<Entry>): Entry {
  return {
    id: "e-1",
    title: "Casa Jardim",
    place: "Porto Alegre, RS",
    year: 2024,
    description: "",
    section_id: "s-arch",
    details: [],
    credits: "",
    videos: [],
    project_id: "p-1",
    project_name: "Casa Jardim",
    photos: [{ id: "f-1", url: "/api/portfolio/photos/f-1" }],
    ...changes,
  };
}

// Two sections, in the office's order: a site type's and one of its own.
const SECTIONS = [
  { id: "s-arch", position: 1, name: "Arquitetura", project_type: "architecture", slug: "architecture" },
  { id: "s-int", position: 2, name: "Interiores", project_type: "interiors", slug: "interiors" },
];

// In the page's order: Arquitetura's pieces (a project of two photos, a loose
// photo), then the piece in no section.
const PORTFOLIO: Portfolio = {
  published: false,
  format: "gallery",
  intro: "",
  links: {},
  sections: SECTIONS,
  entries: [
    entry({ photos: [{ id: "f-1", url: "/api/portfolio/photos/f-1" }, { id: "f-2", url: "/api/portfolio/photos/f-2" }] }),
    entry({ id: "e-3", title: "", place: "", year: null, project_id: null, project_name: null, photos: [{ id: "f-3", url: "/api/portfolio/photos/f-3" }] }),
    entry({ id: "e-2", title: "Loja Centro", place: "", year: null, section_id: null, project_id: null, project_name: null }),
  ],
};

const NO_TYPES = { "GET /api/project-types": () => ({ body: { types: [], stages: [] } }) };

function api(extra = {}) {
  return fakeApi({
    "GET /api/tenant": () => ({ body: TENANT }),
    "GET /api/me": () => ({ body: WITH_PORTFOLIO }),
    "GET /api/portfolio": () => ({ body: PORTFOLIO }),
    "GET /api/onboarding": () => ({ body: { storage_connected: true, office_details: true, has_project: true } }),
    ...extra,
  });
}

describe("the Portfólio tab", () => {
  it("is a tab only where the portfolio is switched on", async () => {
    api({ "GET /api/projects": () => ({ body: [] }) });
    renderAt("/");
    const nav = await screen.findByRole("navigation", { name: "Painel" });
    expect(await within(nav).findByRole("link", { name: "Portfólio" })).toHaveAttribute("href", "/portfolio");
  });

  it("isn't there, nor its address, where the portfolio is off", async () => {
    api({ "GET /api/me": () => ({ body: ME }), "GET /api/projects": () => ({ body: [] }) });
    renderAt("/portfolio");
    expect(await screen.findByRole("heading", { name: "Página não encontrada" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Portfólio" })).toBeNull();
  });

  it("lays the images out in sections by type, each its projects then its loose photos, and Sem tipo last", async () => {
    api();
    renderAt("/portfolio");
    const images = await screen.findByRole("region", { name: /^Imagens/ });
    const sections = within(images).getAllByRole("region");
    expect(sections.map((section) => within(section).getByRole("heading", { level: 3 }).textContent)).toEqual([
      "Arquitetura",
      "Interiores",
      "Sem tipo",
    ]);
    // Arquitetura: a project (two photos) and a loose photo, as two groups, in the office's order.
    const arch = sections[0]!;
    expect(within(arch).getByText("3 fotos · 1 projeto")).toBeInTheDocument();
    const groups = within(arch).getAllByRole("heading", { level: 4 });
    expect(groups.map((group) => group.textContent)).toEqual(["Projetos 1", "Fotos 1"]);
    expect(within(arch).getByRole("button", { name: "Abrir o projeto Casa Jardim" })).toBeInTheDocument();
    expect(within(arch).getByRole("button", { name: "Abrir a foto Foto" })).toBeInTheDocument();
    // Interiores holds nothing yet; Sem tipo the piece in no section.
    expect(within(sections[1]!).getByText(/Nenhuma foto nesta seção ainda/)).toBeInTheDocument();
    expect(within(sections[2]!).getByRole("button", { name: "Abrir a foto Loja Centro" })).toBeInTheDocument();
    // Each section's own drop area, and the way to the portfolio.
    expect(within(arch).getByLabelText("Enviar fotos para Arquitetura")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ver prévia" })).toHaveAttribute("href", "/?previa=1");
  });

  it("publishes with the switch", async () => {
    const sent = api({ "PATCH /api/portfolio": () => ({ body: { ...PORTFOLIO, published: true } }) });
    renderAt("/portfolio");
    await userEvent.click(await screen.findByRole("switch", { name: "Mostrar o portfólio no endereço do escritório" }));
    await waitFor(() => expect(sent.find((call) => call.method === "PATCH")?.body).toEqual({ published: true }));
    expect(await screen.findByRole("link", { name: "Ver portfólio" })).toHaveAttribute("href", "/");
  });

  it("chooses the mosaic format for material made for the networks", async () => {
    const sent = api({ "PATCH /api/portfolio": () => ({ body: { ...PORTFOLIO, format: "mosaic" } }) });
    renderAt("/portfolio");
    const formats = await screen.findByRole("radiogroup", { name: "Formato do portfólio" });
    // Each format is a card: its name, what it is for, and a drawing of its layout.
    const cards = within(formats).getAllByRole("radio");
    expect(cards.map((card) => card.closest("label")?.textContent)).toEqual([
      "GaleriaCapas na horizontal, no mesmo quadro; cada projeto em fotos grandes, uma de cada vez, com setas.",
      "MosaicoCada imagem no formato original, sem capa grande: para o material feito para posts, stories e reels.",
    ]);
    expect(cards.map((card) => card.closest("label")?.querySelector("svg") !== null)).toEqual([true, true]);
    expect(within(formats).getByRole("radio", { name: /Galeria/ })).toBeChecked();
    await userEvent.click(within(formats).getByRole("radio", { name: /Mosaico/ }));
    await waitFor(() => expect(sent.find((call) => call.method === "PATCH")?.body).toEqual({ format: "mosaic" }));
    expect(await screen.findByText("Alterações salvas.")).toBeInTheDocument();
  });

  it("saves the office's social networks", async () => {
    const sent = api({
      "PATCH /api/portfolio": () => ({
        body: { ...PORTFOLIO, links: { instagram: "https://www.instagram.com/alinea" } },
      }),
    });
    renderAt("/portfolio");
    const social = await screen.findByRole("region", { name: "Redes sociais" });
    await userEvent.type(within(social).getByLabelText("Instagram"), "@alinea");
    await userEvent.click(within(social).getByRole("button", { name: "Salvar" }));
    await waitFor(() =>
      expect(sent.find((call) => call.method === "PATCH")?.body).toEqual({ links: { instagram: "@alinea" } }),
    );
    // As the server keeps it.
    await waitFor(() =>
      expect(within(social).getByLabelText("Instagram")).toHaveValue("https://www.instagram.com/alinea"),
    );
  });

  it("offers archived projects too, marked, since finished work is what a portfolio shows", async () => {
    const sent = api({
      "GET /api/projects": () => ({
        body: [{ id: "p-9", name: "Casa Serra", client_name: "Família Prado", slug: "casa-serra", status: "archived", cover_url: null }],
      }),
    });
    renderAt("/portfolio");
    await userEvent.click(await screen.findByRole("button", { name: "Adicionar de um projeto" }));
    const dialog = await screen.findByRole("dialog", { name: "Escolher projeto" });
    expect(await within(dialog).findByText("Família Prado · Arquivado")).toBeInTheDocument();
    expect(sent.find((call) => call.path === "/api/projects")?.query).toBe("?archived=true");
  });

  it("reorders the sections, the public menu's order, by sending the whole new order", async () => {
    const sent = api({ "PUT /api/portfolio/sections/order": () => ({ body: PORTFOLIO }) });
    renderAt("/portfolio");
    const images = await screen.findByRole("region", { name: /^Imagens/ });
    const [arch] = within(images).getAllByRole("region");
    expect(within(arch!).getByRole("button", { name: "Mover para cima" })).toBeDisabled();
    await userEvent.click(within(arch!).getByRole("button", { name: "Mover para baixo" }));
    await waitFor(() =>
      expect(sent.find((call) => call.method === "PUT")?.body).toEqual({ sections: ["s-int", "s-arch"] }),
    );
  });

  it("opens one dialog for every drop, and adds the photos as loose pieces of the section, last to first", async () => {
    const sent = api({ "POST /api/portfolio/photos": () => ({ body: PORTFOLIO }) });
    renderAt("/portfolio");
    const input = await screen.findByLabelText("Enviar fotos para Interiores");
    const files = [new File(["a"], "sala.jpg", { type: "image/jpeg" }), new File(["b"], "quarto.jpg", { type: "image/jpeg" })];
    await userEvent.upload(input, files);
    const dialog = await screen.findByRole("dialog", { name: "2 fotos" });
    // Everything optional: the section it was dropped on, loose photos, no captions.
    expect(within(dialog).getByRole("combobox", { name: "Seção" })).toHaveValue("s-int");
    expect(within(dialog).getByRole("radio", { name: "Fotos soltas" })).toBeChecked();
    await userEvent.type(within(dialog).getByLabelText("Legenda da foto 1"), "Sala");
    await userEvent.click(within(dialog).getByRole("button", { name: "Adicionar" }));
    await waitFor(() => expect(sent.filter((call) => call.path === "/api/portfolio/photos")).toHaveLength(2));
    expect(await screen.findByText("2 fotos adicionadas.")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("after a failed upload, sends only the photos still missing, and keeps the captions to loose photos", async () => {
    let calls = 0;
    const sent = api({
      "POST /api/portfolio/photos": () =>
        ++calls === 2 ? { status: 503, body: { error: "drive_connect_failed" } } : { body: PORTFOLIO },
    });
    renderAt("/portfolio");
    const input = await screen.findByLabelText("Enviar fotos para Interiores");
    await userEvent.upload(input, [1, 2, 3].map((n) => new File([`${n}`], `${n}.jpg`, { type: "image/jpeg" })));
    const dialog = await screen.findByRole("dialog", { name: "3 fotos" });
    // Captions belong to loose photos: a project's photos have none, so the boxes go.
    expect(within(dialog).getAllByLabelText(/^Legenda da foto/)).toHaveLength(3);
    await userEvent.click(within(dialog).getByRole("radio", { name: "Um projeto novo" }));
    expect(within(dialog).queryByLabelText(/^Legenda da foto/)).toBeNull();
    // Into an existing project, the photos take its section: the choice follows it.
    await userEvent.click(within(dialog).getByRole("radio", { name: "Em um projeto" }));
    expect(within(dialog).getByRole("combobox", { name: "Seção" })).toBeDisabled();
    expect(within(dialog).getByRole("combobox", { name: "Seção" })).toHaveValue("s-arch"); // Casa Jardim's
    await userEvent.click(within(dialog).getByRole("radio", { name: "Fotos soltas" }));
    expect(within(dialog).getByRole("combobox", { name: "Seção" })).toBeEnabled();
    await userEvent.click(within(dialog).getByRole("button", { name: "Adicionar" }));
    expect(await within(dialog).findByText("O envio parou em 1 de 3. As que faltam podem ser enviadas de novo.")).toBeInTheDocument();
    // What was sent went to Interiores: the section can't change under the rest.
    expect(within(dialog).getByRole("combobox", { name: "Seção" })).toBeDisabled();
    expect(sent.filter((call) => call.path === "/api/portfolio/photos")).toHaveLength(2);
    await userEvent.click(within(dialog).getByRole("button", { name: "Enviar as que faltam" }));
    // Two more, never the one already in: four calls for three photos.
    await waitFor(() => expect(sent.filter((call) => call.path === "/api/portfolio/photos")).toHaveLength(4));
    expect(await screen.findByText("3 fotos adicionadas.")).toBeInTheDocument();
  });

  it("can't be closed while the photos go up, so the upload's outcome is never hidden", async () => {
    let answer: (reply: { body: unknown }) => void = () => undefined;
    api({ "POST /api/portfolio/photos": () => new Promise((resolve) => (answer = resolve)) });
    renderAt("/portfolio");
    const input = await screen.findByLabelText("Enviar fotos para Interiores");
    await userEvent.upload(input, [new File(["a"], "sala.jpg", { type: "image/jpeg" })]);
    const dialog = await screen.findByRole("dialog", { name: "1 foto" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Adicionar" }));
    expect(await within(dialog).findByText("Enviando 0 de 1…")).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Fechar" }));
    expect(screen.getByRole("dialog", { name: "1 foto" })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Fechar" })).toBeDisabled();
    within(dialog).getByRole("combobox", { name: "Em um projeto" }).focus();
    await userEvent.keyboard("{Escape}");
    expect(screen.getByRole("dialog", { name: "1 foto" })).toBeInTheDocument();
    answer({ body: PORTFOLIO });
    expect(await screen.findByText("1 foto adicionada.")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("makes one project of a drop when asked, opened on its photos", async () => {
    const made = { ...PORTFOLIO, entries: [entry({ id: "e-new", title: "Casa Nova", photos: [], project_id: null }), ...PORTFOLIO.entries] };
    const sent = api({
      "POST /api/portfolio/entries": () => ({ body: made }),
      "POST /api/portfolio/entries/e-new/photos": () => ({ body: made }),
    });
    renderAt("/portfolio");
    const input = await screen.findByLabelText("Enviar um projeto inteiro para Interiores");
    await userEvent.upload(input, [new File(["a"], "a.jpg", { type: "image/jpeg" }), new File(["b"], "b.jpg", { type: "image/jpeg" })]);
    const dialog = await screen.findByRole("dialog", { name: "2 fotos" });
    expect(within(dialog).getByRole("radio", { name: "Um projeto novo" })).toBeChecked();
    await userEvent.type(within(dialog).getByLabelText("Título do projeto"), "Casa Nova");
    await userEvent.click(within(dialog).getByRole("button", { name: "Adicionar" }));
    await waitFor(() =>
      expect(sent.find((call) => call.path === "/api/portfolio/entries")?.body).toEqual({
        title: "Casa Nova",
        place: "",
        description: "",
        section_id: "s-int",
      }),
    );
    await waitFor(() => expect(sent.filter((call) => call.path === "/api/portfolio/entries/e-new/photos")).toHaveLength(2));
    expect(await screen.findByText("Projeto criado.")).toBeInTheDocument();
  });

  it("groups selected pieces into a project from the bar, the first as its cover", async () => {
    const sent = api({ "POST /api/portfolio/entries/e-3/merge": () => ({ body: PORTFOLIO }) });
    renderAt("/portfolio");
    await userEvent.click(await screen.findByRole("checkbox", { name: "Selecionar Foto" }));
    const bar = screen.getByRole("toolbar", { name: "Itens selecionados" });
    expect(within(bar).getByText("1 selecionado")).toBeInTheDocument();
    expect(within(bar).getByRole("button", { name: "Agrupar em projeto" })).toBeDisabled();
    await userEvent.click(screen.getByRole("checkbox", { name: "Selecionar Loja Centro" }));
    expect(within(bar).getByText("2 selecionados")).toBeInTheDocument();
    await userEvent.click(within(bar).getByRole("button", { name: "Agrupar em projeto" }));
    await waitFor(() =>
      expect(sent.find((call) => call.method === "POST")?.body).toEqual({ entries: ["e-2"] }),
    );
    expect(await screen.findByText("Projeto criado.")).toBeInTheDocument();
  });

  it("moves selected pieces to another section from the bar", async () => {
    const sent = api({ "PATCH /api/portfolio/entries/e-2": () => ({ body: PORTFOLIO }) });
    renderAt("/portfolio");
    await userEvent.click(await screen.findByRole("checkbox", { name: "Selecionar Loja Centro" }));
    const bar = screen.getByRole("toolbar", { name: "Itens selecionados" });
    await userEvent.selectOptions(within(bar).getByRole("combobox", { name: "Mover para…" }), "Interiores");
    await waitFor(() => expect(sent.find((call) => call.method === "PATCH")?.body).toEqual({ section_id: "s-int" }));
    expect(await screen.findByText("Movido para Interiores.")).toBeInTheDocument();
  });

  it("opens a photo on its sheet: a caption and a section, both optional", async () => {
    const sent = api({ "PATCH /api/portfolio/entries/e-3": () => ({ body: PORTFOLIO }) });
    renderAt("/portfolio");
    await userEvent.click(await screen.findByRole("button", { name: "Abrir a foto Foto" }));
    const sheet = await screen.findByRole("dialog", { name: "Foto" });
    await userEvent.type(within(sheet).getByLabelText("Legenda"), "Sala de estar");
    await userEvent.click(within(sheet).getByRole("button", { name: "Salvar" }));
    await waitFor(() =>
      expect(sent.find((call) => call.method === "PATCH")?.body).toEqual({ title: "Sala de estar", section_id: "s-arch" }),
    );
  });

  it("adds a section: one of the site's types the office hasn't yet, or a name of its own", async () => {
    const sent = api({
      "GET /api/project-types": () => ({
        body: {
          types: [
            { key: "architecture", label: "Projeto Arquitetônico", stages: [] },
            { key: "landscaping", label: "Paisagismo", stages: [] },
          ],
          stages: [],
        },
      }),
      "POST /api/portfolio/sections": () => ({ body: PORTFOLIO }),
    });
    renderAt("/portfolio");
    await userEvent.click(await screen.findByRole("button", { name: "+ Nova seção" }));
    const dialog = await screen.findByRole("dialog", { name: "Nova seção" });
    // Arquitetura is a section already: only Paisagismo is offered.
    expect(await within(dialog).findByRole("button", { name: "Paisagismo" })).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "Arquitetura" })).toBeNull();
    await userEvent.type(within(dialog).getByLabelText("Nome da seção"), "Stories");
    await userEvent.click(within(dialog).getByRole("button", { name: "Criar" }));
    await waitFor(() => expect(sent.find((call) => call.method === "POST")?.body).toEqual({ label: "Stories" }));
    expect(await screen.findByText("Seção “Stories” criada.")).toBeInTheDocument();
  });

  it("copies the portfolio's link, or a section's, to share", async () => {
    const writeText = vi.fn(() => Promise.resolve());
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText }, share: undefined });
    api();
    renderAt("/portfolio");
    await userEvent.click(await screen.findByRole("button", { name: "Compartilhar" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(window.location.origin + "/"));
    expect(await screen.findByText("Link copiado.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Compartilhar a seção Interiores" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(window.location.origin + "/?tipo=interiors"));
  });
});

describe("a work's editor", () => {
  it("opens on the photos, asks for the title, and folds the rest away until something is there", async () => {
    const bare = { ...PORTFOLIO, entries: [entry({ place: "", year: null, section_id: null, project_id: null })] };
    api({ ...NO_TYPES, "GET /api/portfolio": () => ({ body: bare }) });
    renderAt("/portfolio/e-1"); // a bare work: nothing but its title and a photo
    const title = await screen.findByLabelText("Título");
    const photos = screen.getByRole("region", { name: /^Fotos/ });
    expect(photos.compareDocumentPosition(title) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // The videos right after the photos, before the words; no "Situação" anywhere.
    const videos = screen.getByRole("region", { name: /^Vídeos/ });
    expect(videos.compareDocumentPosition(title) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(photos.compareDocumentPosition(videos) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.queryByText("Situação")).toBeNull();
    // The work as the public page shows it, in a new tab: the preview while unpublished.
    expect(screen.getByRole("link", { name: "Ver no portfólio" })).toHaveAttribute("href", "/?projeto=e-1&previa=1");
    const more = screen.getByText("Mais informações").closest("details")!;
    expect(more.open).toBe(false);
    await userEvent.click(screen.getByText("Mais informações"));
    expect(more.open).toBe(true);
    expect(screen.getByLabelText("Local")).toHaveValue("");
  });

  it("shows the rest unfolded where the work already has some of it", async () => {
    api({ ...NO_TYPES });
    renderAt("/portfolio/e-1"); // a place, a year and a type
    await screen.findByLabelText("Título");
    expect(screen.getByText("Mais informações").closest("details")!.open).toBe(true);
  });

  it("files the work under a section, for the public page's menu", async () => {
    const sent = api({ ...NO_TYPES, "PATCH /api/portfolio/entries/e-1": () => ({ body: PORTFOLIO }) });
    renderAt("/portfolio/e-1");
    const section = await screen.findByRole("combobox", { name: "Seção" });
    await waitFor(() => expect(section).toHaveValue("s-arch"));
    await userEvent.selectOptions(section, "Interiores");
    await userEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await waitFor(() =>
      expect(sent.find((call) => call.method === "PATCH")?.body).toMatchObject({ section_id: "s-int" }),
    );
  });

  it("needs no title: a project may be saved without one", async () => {
    const sent = api({ ...NO_TYPES, "PATCH /api/portfolio/entries/e-1": () => ({ body: PORTFOLIO }) });
    renderAt("/portfolio/e-1");
    const title = await screen.findByLabelText("Título");
    await userEvent.clear(title);
    expect(screen.getByRole("button", { name: "Salvar" })).toBeEnabled();
    await userEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await waitFor(() => expect(sent.find((call) => call.method === "PATCH")?.body).toMatchObject({ title: "" }));
  });

  it("ungroups a project from its editor: its photos after the first become pieces of their own", async () => {
    const sent = api({ ...NO_TYPES, "POST /api/portfolio/entries/e-1/split": () => ({ body: PORTFOLIO }) });
    renderAt("/portfolio/e-1");
    await userEvent.click(await screen.findByRole("button", { name: "Desfazer projeto" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Desfazer o projeto?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Desfazer projeto" }));
    await waitFor(() => expect(sent.some((call) => call.path === "/api/portfolio/entries/e-1/split")).toBe(true));
    expect(await screen.findByText("Projeto desfeito. As fotos continuam no portfólio.")).toBeInTheDocument();
  });

  const DETAIL_TYPES = {
    "GET /api/portfolio/detail-types": () => ({
      body: [
        { key: "built_area", label: "Área construída", type: "area" },
        { key: "start_date", label: "Início", type: "date" },
        { key: "responsible", label: "Responsável", type: "text" },
      ],
    }),
  };
  const WITH_SHEET = {
    ...PORTFOLIO,
    entries: [
      entry({ details: [{ key: "responsible", label: "Responsável", type: "text", value: "Laura Mendes" }] }),
    ],
  };

  it("keeps the work's sheet: built-in details, typed, and lines with the office's own name", async () => {
    const sent = api({
      ...NO_TYPES,
      ...DETAIL_TYPES,
      "GET /api/portfolio": () => ({ body: WITH_SHEET }),
      "PATCH /api/portfolio/entries/e-1": () => ({ body: WITH_SHEET }),
    });
    renderAt("/portfolio/e-1");
    const sheet = await screen.findByRole("group", { name: "Informações" });
    expect(within(sheet).getByLabelText("Responsável")).toHaveValue("Laura Mendes");
    // A built-in detail, once each: the menu offers the ones not yet in the sheet.
    await userEvent.click(within(sheet).getByRole("button", { name: "Adicionar informação" }));
    // The project page's details not yet in the sheet, then what a portfolio's
    // sheet usually names (ready-made own lines), then a line of any name.
    expect(screen.getAllByRole("menuitem").map((item) => item.textContent)).toEqual([
      "Área construída",
      "Início",
      "Fotografia",
      "Construtora",
      "Marcenaria",
      "Paisagismo",
      "Iluminação",
      "Estrutura",
      "Colaboradores",
      "Fornecedores",
      "Outra informação…",
    ]);
    await userEvent.click(screen.getByRole("menuitem", { name: "Área construída" }));
    await userEvent.type(within(sheet).getByLabelText("Área construída"), "1.250,5");
    await userEvent.click(within(sheet).getByRole("button", { name: "Adicionar informação" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Início" }));
    await userEvent.type(within(sheet).getByLabelText("Início"), "2024-03-02");
    // A ready-made own line comes with its name; only its value is typed.
    await userEvent.click(within(sheet).getByRole("button", { name: "Adicionar informação" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Fotografia" }));
    expect(within(sheet).getByLabelText("Nome da informação")).toHaveValue("Fotografia");
    await userEvent.type(within(sheet).getByLabelText("Valor"), "Estúdio Luz");
    // Once in the sheet, it isn't offered again; a line of any name always is.
    await userEvent.click(within(sheet).getByRole("button", { name: "Adicionar informação" }));
    expect(screen.queryByRole("menuitem", { name: "Fotografia" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("menuitem", { name: "Outra informação…" }));
    await userEvent.type(within(sheet).getAllByLabelText("Nome da informação")[1]!, "Construção");
    await userEvent.type(within(sheet).getAllByLabelText("Valor")[1]!, "Obra Prima");
    await userEvent.click(within(sheet).getByRole("button", { name: "Remover Responsável" }));
    await userEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await waitFor(() =>
      expect(sent.find((call) => call.method === "PATCH")?.body).toMatchObject({
        details: [
          { key: "built_area", value: "1250.5" },
          { key: "start_date", value: "2024-03-02" },
          { label: "Fotografia", value: "Estúdio Luz" },
          { label: "Construção", value: "Obra Prima" },
        ],
      }),
    );
  });

  it("stops at twenty lines, saying so, instead of letting a sheet grow past what the server keeps", async () => {
    const full = Array.from({ length: 20 }, (_, n) => ({ key: null, label: `Linha ${n + 1}`, type: "text" as const, value: "x" }));
    api({
      ...NO_TYPES,
      ...DETAIL_TYPES,
      "GET /api/portfolio": () => ({ body: { ...PORTFOLIO, entries: [entry({ details: full })] } }),
    });
    renderAt("/portfolio/e-1");
    const sheet = await screen.findByRole("group", { name: "Informações" });
    expect(within(sheet).getByText("Cada projeto pode ter até 20 informações.")).toBeInTheDocument();
    expect(within(sheet).queryByRole("button", { name: "Adicionar informação" })).not.toBeInTheDocument();
    await userEvent.click(within(sheet).getByRole("button", { name: "Remover Linha 20" }));
    expect(within(sheet).getByRole("button", { name: "Adicionar informação" })).toBeInTheDocument();
  });

  it("won't save a sheet with an area that isn't one, or an own line without its name", async () => {
    api({ ...NO_TYPES, ...DETAIL_TYPES });
    renderAt("/portfolio/e-1");
    const sheet = await screen.findByRole("group", { name: "Informações" });
    await userEvent.click(within(sheet).getByRole("button", { name: "Adicionar informação" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Área construída" }));
    const area = within(sheet).getByLabelText("Área construída");
    await userEvent.type(area, "grande");
    expect(area).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("button", { name: "Salvar" })).toBeDisabled();
    await userEvent.clear(area);
    await userEvent.type(area, "180");
    expect(screen.getByRole("button", { name: "Salvar" })).toBeEnabled();
    await userEvent.click(within(sheet).getByRole("button", { name: "Adicionar informação" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Outra informação…" }));
    await userEvent.type(within(sheet).getByLabelText("Valor"), "Estúdio Luz");
    expect(screen.getByRole("button", { name: "Salvar" })).toBeDisabled(); // no name yet
    await userEvent.type(within(sheet).getByLabelText("Nome da informação"), "Fotografia");
    expect(screen.getByRole("button", { name: "Salvar" })).toBeEnabled();
  });
});

describe("picking a project's images", () => {
  it("offers both images of a before-and-after comparison, each under its own name (A46)", async () => {
    const image = (key: string, name: string) => ({ key, name, kind: "image", size: 10, modified_at: "2026-11-01T12:00:00Z", older: [] });
    api({
      ...NO_TYPES,
      "GET /api/projects": () => ({
        body: [{ id: "p-1", name: "Casa Jardim", client_name: "Família Oliveira", slug: "casa-jardim", status: "active", cover_url: null }],
      }),
      "GET /api/pages/casa-jardim/files": () => ({
        body: {
          stages: [
            {
              position: 1,
              groups: [
                {
                  folder: null,
                  files: [
                    {
                      ...image("k-b", "Cozinha"),
                      comparison: {
                        after: image("k-a", "Cozinha (depois).jpg"),
                        before_label: null,
                        after_label: null,
                        before_name: "Cozinha (antes).jpg",
                        after_name: "Cozinha (depois).jpg",
                      },
                    },
                  ],
                },
              ],
            },
          ],
        },
      }),
    });
    renderAt("/portfolio/e-1");
    await userEvent.click(await screen.findByRole("button", { name: "Escolher fotos de um projeto" }));
    const dialog = await screen.findByRole("dialog", { name: "Fotos de Casa Jardim" });
    expect(await within(dialog).findByText("Cozinha (antes).jpg")).toBeInTheDocument();
    expect(within(dialog).getByText("Cozinha (depois).jpg")).toBeInTheDocument();
    expect(within(dialog).getAllByRole("checkbox")).toHaveLength(2);
  });
});

describe("a work's before and after (A46)", () => {
  const THREE = [
    { id: "f-1", url: "/api/portfolio/photos/f-1" },
    { id: "f-2", url: "/api/portfolio/photos/f-2" },
    { id: "f-3", url: "/api/portfolio/photos/f-3" },
  ];

  it("marks as the cover the first photo the page shows, never a comparison's after", async () => {
    const photos = [THREE[0]!, { ...THREE[1]!, comparison: { after: "f-1", before_label: null, after_label: null } }, THREE[2]!];
    api({ ...NO_TYPES, ...COMPARING, "GET /api/portfolio": () => ({ body: { ...PORTFOLIO, entries: [entry({ photos })] } }) });
    renderAt("/portfolio/e-1");
    const tiles = await screen.findAllByRole("listitem");
    const second = tiles.find((tile) => within(tile).queryByAltText("Foto 2"))!;
    expect(within(second).getByText("Capa")).toBeInTheDocument();
  });

  it("lists the work with that same photo as its thumbnail", async () => {
    const photos = [THREE[0]!, { ...THREE[1]!, comparison: { after: "f-1", before_label: null, after_label: null } }, THREE[2]!];
    api({ ...NO_TYPES, ...COMPARING, "GET /api/portfolio": () => ({ body: { ...PORTFOLIO, entries: [entry({ photos })] } }) });
    renderAt("/portfolio");
    const tile = await screen.findByRole("button", { name: "Abrir o projeto Casa Jardim" });
    expect(within(tile).getByRole("presentation")).toHaveAttribute("src", "/api/portfolio/photos/f-2?size=card");
  });

  it("offers no \"Antes e depois\" when comparisons are switched off for the office", async () => {
    api({ ...NO_TYPES, "GET /api/portfolio": () => ({ body: { ...PORTFOLIO, entries: [entry({ photos: THREE })] } }) });
    renderAt("/portfolio/e-1");
    await screen.findByAltText("Foto 3");
    expect(screen.queryByRole("button", { name: "Antes e depois" })).not.toBeInTheDocument();
  });

  it("compares a photo with another of the work's, naming the sides", async () => {
    const sent = api({
      ...NO_TYPES, ...COMPARING,
      "GET /api/portfolio": () => ({ body: { ...PORTFOLIO, entries: [entry({ photos: THREE })] } }),
      "PUT /api/portfolio/photos/f-2/comparison": () => ({ body: PORTFOLIO }),
    });
    renderAt("/portfolio/e-1");
    const tiles = await screen.findAllByRole("button", { name: "Antes e depois" });
    await userEvent.click(tiles[1]!); // the second photo, as the "before"
    const dialog = await screen.findByRole("dialog", { name: "Antes e depois" });
    const choices = within(dialog).getByRole("radiogroup", { name: "Foto do “depois”" });
    // Every other photo of the work, never the "before" itself.
    expect(within(choices).getAllByRole("radio").map((radio) => radio.getAttribute("aria-label"))).toEqual([
      "Foto 1",
      "Foto 3",
    ]);
    expect(within(dialog).getByRole("button", { name: "Salvar" })).toBeDisabled();
    await userEvent.click(within(choices).getByRole("radio", { name: "Foto 3" }));
    expect(within(dialog).getByRole("slider")).toBeInTheDocument(); // the preview
    await userEvent.type(within(dialog).getByRole("textbox", { name: "Rótulo de “Depois” (opcional)" }), "Obra");
    await userEvent.click(within(dialog).getByRole("button", { name: "Salvar" }));
    await waitFor(() =>
      expect(sent.find((call) => call.method === "PUT")?.body).toEqual({
        after: "f-3",
        before_label: null,
        after_label: "Obra",
      }),
    );
  });

  it("marks both photos of a comparison, offers it only where a photo is free, and undoes it", async () => {
    const photos = [{ ...THREE[0]!, comparison: { after: "f-3", before_label: null, after_label: null } }, THREE[1]!, THREE[2]!];
    const sent = api({
      ...NO_TYPES, ...COMPARING,
      "GET /api/portfolio": () => ({ body: { ...PORTFOLIO, entries: [entry({ photos })] } }),
      "PUT /api/portfolio/photos/f-1/comparison": () => ({ body: PORTFOLIO }),
    });
    renderAt("/portfolio/e-1");
    expect(await screen.findByText("Depois da foto 1")).toBeInTheDocument();
    expect(screen.getAllByText("Capa")).toHaveLength(1);
    // Only the "before" photo has the tool: its "after" goes with it, and the
    // second photo has no free photo left to compare with.
    const tiles = screen.getAllByRole("button", { name: "Antes e depois" });
    expect(tiles).toHaveLength(1);
    await userEvent.click(tiles[0]!);
    const own = await screen.findByRole("dialog", { name: "Antes e depois" });
    await userEvent.click(within(own).getByRole("button", { name: "Desfazer comparação" }));
    await waitFor(() => expect(sent.find((call) => call.method === "PUT")?.body).toMatchObject({ after: null }));
  });
});

describe("a work's videos", () => {
  const MP4 = () => new File(["mp4"], "obra.mp4", { type: "video/mp4" });
  const videoInput = () => document.querySelector<HTMLInputElement>('input[accept="video/mp4,video/webm"]')!;

  it("are sent with a frame of each, the poster, and listed", async () => {
    const poster = new File(["jpg"], "capa.jpg", { type: "image/jpeg" });
    vi.mocked(videoPoster).mockResolvedValue(poster);
    const video = { id: "v-1", url: "/api/portfolio/videos/v-1", poster_url: "/api/portfolio/videos/v-1/poster" };
    vi.mocked(sendVideo).mockResolvedValue({ ...PORTFOLIO, entries: [entry({ videos: [video] })] });
    api(NO_TYPES);
    renderAt("/portfolio/e-1");
    const videos = await screen.findByRole("region", { name: /Vídeos/ });
    expect(within(videos).getByText("Nenhum vídeo ainda.")).toBeInTheDocument();
    const file = MP4();
    fireEvent.change(videoInput(), { target: { files: [file] } });
    expect(await screen.findByText("1 vídeo adicionado.")).toBeInTheDocument();
    expect(vi.mocked(sendVideo).mock.calls[0]!.slice(0, 3)).toEqual(["e-1", file, poster]);
    expect(within(videos).getByRole("img", { name: "Vídeo 1" })).toHaveAttribute("src", video.poster_url);
  });

  it("aren't sent when the browser can't play them, nor in another format", async () => {
    vi.mocked(videoPoster).mockRejectedValue(new Error("video"));
    api(NO_TYPES);
    renderAt("/portfolio/e-1");
    await screen.findByRole("region", { name: /Vídeos/ });
    fireEvent.change(videoInput(), { target: { files: [MP4()] } });
    expect(await screen.findByText(/Não foi possível abrir “obra.mp4” no navegador/)).toBeInTheDocument();
    fireEvent.change(videoInput(), { target: { files: [new File(["mov"], "obra.mov", { type: "video/quicktime" })] } });
    expect(await screen.findByText(/Envie vídeos em MP4 ou WebM/)).toBeInTheDocument();
    expect(sendVideo).not.toHaveBeenCalled();
  });
});

describe("parsedArea", () => {
  it("reads areas as people type them", () => {
    expect(parsedArea("")).toBeNull();
    expect(parsedArea("180")).toBe(180);
    expect(parsedArea("85,5 m²")).toBe(85.5);
    expect(parsedArea("85.5")).toBe(85.5);
    expect(parsedArea("1.250,75")).toBe(1250.75);
    // A separator before three digits groups thousands, the Brazilian or the English way.
    expect(parsedArea("1.250")).toBe(1250);
    expect(parsedArea("12.000")).toBe(12000);
    expect(parsedArea("1.250.000")).toBe(1250000);
    expect(parsedArea("1,250")).toBe(1250);
    expect(parsedArea("1,250.75")).toBe(1250.75);
    expect(parsedArea("0,5")).toBe(0.5);
    expect(parsedArea("2,25")).toBe(2.25);
    expect(parsedArea("0")).toBe(0); // as a project's details allow
    expect(parsedArea("10.000.000")).toBe(10000000);
    expect(parsedArea("abc")).toBeUndefined();
  });
});

describe("moved", () => {
  const items = [{ id: "a" }, { id: "b" }, { id: "c" }];
  it("swaps an item with its neighbour, and stays put at either end", () => {
    expect(moved(items, 1, -1)).toEqual(["b", "a", "c"]);
    expect(moved(items, 1, 1)).toEqual(["a", "c", "b"]);
    expect(moved(items, 0, -1)).toEqual(["a", "b", "c"]);
    expect(moved(items, 2, 1)).toEqual(["a", "b", "c"]);
  });
});
