import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, ME, renderAt, TENANT } from "../test/render";
import { moved, type Entry, type Portfolio } from "./portfolio";

afterEach(() => vi.unstubAllGlobals());

const WITH_PORTFOLIO = { ...ME, features: ["portfolio"] };

function entry(changes: Partial<Entry>): Entry {
  return {
    id: "e-1",
    title: "Casa Jardim",
    place: "Porto Alegre, RS",
    year: 2024,
    description: "",
    project_id: "p-1",
    project_name: "Casa Jardim",
    photos: [{ id: "f-1", url: "/api/portfolio/photos/f-1" }],
    ...changes,
  };
}

const PORTFOLIO: Portfolio = {
  published: false,
  intro: "",
  entries: [entry({}), entry({ id: "e-2", title: "Loja Centro", place: "", year: null, photos: [], project_id: null })],
};

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

describe("moved", () => {
  const items = [{ id: "a" }, { id: "b" }, { id: "c" }];
  it("swaps an item with its neighbour, and stays put at either end", () => {
    expect(moved(items, 1, -1)).toEqual(["b", "a", "c"]);
    expect(moved(items, 1, 1)).toEqual(["a", "c", "b"]);
    expect(moved(items, 0, -1)).toEqual(["a", "b", "c"]);
    expect(moved(items, 2, 1)).toEqual(["a", "b", "c"]);
  });
});
