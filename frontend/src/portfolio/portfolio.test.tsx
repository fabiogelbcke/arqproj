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
    area: null,
    status: null,
    team: "",
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

  it("sends a work's facts with its other texts, the area as a number", async () => {
    const sent = api({ ...NO_TYPES, "PATCH /api/portfolio/entries/e-1": () => ({ body: PORTFOLIO }) });
    renderAt("/portfolio/e-1");
    await userEvent.type(await screen.findByLabelText("Área (m²)"), "1.250,5");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Situação" }), "Concluído");
    await userEvent.type(screen.getByLabelText("Equipe"), "Laura Mendes");
    await userEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await waitFor(() =>
      expect(sent.find((call) => call.method === "PATCH")?.body).toMatchObject({
        area: 1250.5,
        status: "completed",
        team: "Laura Mendes",
      }),
    );
  });

  it("won't save an area that isn't one", async () => {
    api(NO_TYPES);
    renderAt("/portfolio/e-1");
    const area = await screen.findByLabelText("Área (m²)");
    await userEvent.type(area, "grande");
    expect(area).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("button", { name: "Salvar" })).toBeDisabled();
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
    expect(parsedArea("1.250,75")).toBe(1250.75);
    expect(parsedArea("0")).toBeUndefined();
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
