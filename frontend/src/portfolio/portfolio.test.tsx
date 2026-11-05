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
}));

afterEach(() => {
  vi.unstubAllGlobals();
  vi.mocked(videoPoster).mockReset();
  vi.mocked(sendVideo).mockReset();
});

const WITH_PORTFOLIO = { ...ME, features: ["portfolio"] };

function entry(changes: Partial<Entry>): Entry {
  return {
    id: "e-1",
    title: "Casa Jardim",
    place: "Porto Alegre, RS",
    year: 2024,
    description: "",
    project_type: "architecture",
    status: null,
    details: [],
    credits: "",
    videos: [],
    project_id: "p-1",
    project_name: "Casa Jardim",
    photos: [{ id: "f-1", url: "/api/portfolio/photos/f-1" }],
    ...changes,
  };
}

const PORTFOLIO: Portfolio = {
  published: false,
  format: "gallery",
  intro: "",
  links: {},
  entries: [entry({}), entry({ id: "e-2", title: "Loja Centro", place: "", year: null, photos: [], project_id: null })],
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

  it("lists the works in order and says which won't show for lack of photos", async () => {
    api();
    renderAt("/portfolio");
    const works = await screen.findByRole("region", { name: /Projetos no portfólio/ });
    const rows = within(works).getAllByRole("listitem");
    expect(within(rows[0]!).getByText("Porto Alegre, RS · 2024")).toBeInTheDocument();
    expect(within(rows[0]!).getByText("1 foto")).toBeInTheDocument();
    expect(within(rows[1]!).getByText("Sem fotos: não aparece no portfólio")).toBeInTheDocument();
    expect(within(rows[0]!).getByRole("button", { name: "Mover para cima" })).toBeDisabled();
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
      "GaleriaCapas na horizontal, no mesmo quadro; cada projeto em fotos grandes, uma após a outra.",
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

  it("moves a work down by sending the whole new order", async () => {
    const sent = api({ "PUT /api/portfolio/order": () => ({ body: PORTFOLIO }) });
    renderAt("/portfolio");
    const works = await screen.findByRole("region", { name: /Projetos no portfólio/ });
    await userEvent.click(within(within(works).getAllByRole("listitem")[0]!).getByRole("button", { name: "Mover para baixo" }));
    await waitFor(() =>
      expect(sent.find((call) => call.method === "PUT")?.body).toEqual({ entries: ["e-2", "e-1"] }),
    );
  });
});

describe("a work's editor", () => {
  it("opens on the photos, asks for the title, and folds the rest away until something is there", async () => {
    const bare = { ...PORTFOLIO, entries: [entry({ place: "", year: null, project_type: null, project_id: null })] };
    api({ ...NO_TYPES, "GET /api/portfolio": () => ({ body: bare }) });
    renderAt("/portfolio/e-1"); // a bare work: nothing but its title and a photo
    const title = await screen.findByLabelText("Título");
    const photos = screen.getByRole("region", { name: /^Fotos/ });
    expect(photos.compareDocumentPosition(title) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
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

  it("files the work under a type, for the public page's menu", async () => {
    const sent = api({
      "GET /api/project-types": () => ({
        body: {
          types: [
            { key: "architecture", label: "Projeto Arquitetônico", stages: [] },
            { key: "interiors", label: "Projeto de Interiores", stages: [] },
          ],
          stages: [],
        },
      }),
      "PATCH /api/portfolio/entries/e-1": () => ({ body: PORTFOLIO }),
    });
    renderAt("/portfolio/e-1");
    const type = await screen.findByRole("combobox", { name: "Tipo" });
    await waitFor(() => expect(type).toHaveValue("architecture"));
    await userEvent.selectOptions(type, "Interiores");
    await userEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await waitFor(() =>
      expect(sent.find((call) => call.method === "PATCH")?.body).toMatchObject({ project_type: "interiors" }),
    );
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
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Situação" }), "Concluído");
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
        status: "completed",
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
