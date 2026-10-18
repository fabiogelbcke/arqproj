import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fakeApi, ME, notSignedIn, TENANT } from "../../test/render";
import { EXAMPLE_SLUG } from "./address";
import { ExampleApp } from "./ExampleApp";

// Driver.js draws in the browser; here, what the explore tour is given and does.
const driven = vi.hoisted(() => ({ configs: [] as Record<string, any>[], destroy: vi.fn(), drive: vi.fn() }));
vi.mock("driver.js", () => ({
  driver: (config: Record<string, any>) => {
    driven.configs.push(config);
    return { drive: driven.drive, destroy: driven.destroy };
  },
}));
// The setup tour (for the office's real projects) must not start here.
const setupTour = vi.hoisted(() => ({ startTour: vi.fn() }));
vi.mock("../Tour", () => setupTour);

beforeEach(() => {
  driven.configs.length = 0;
  vi.clearAllMocks();
  window.history.pushState({}, "", `/${EXAMPLE_SLUG}`);
});
afterEach(async () => {
  // Each visit's tour ends with its test (one tour runs at a time).
  await waitFor(() => expect(driven.configs.length).toBeGreaterThan(0));
  driven.configs.forEach((config) => config.onDestroyStarted());
  vi.unstubAllGlobals();
});

/** The example, with what reaches "the server" recorded. */
function visit(signedIn: boolean) {
  const sent = fakeApi({
    "GET /api/tenant": () => ({ body: { ...TENANT, logo_url: null, logo_dark_url: null } }),
    "GET /api/me": () =>
      signedIn ? { body: { ...ME, page_tour_seen: false, csrf_token: "csrf-123" } } : notSignedIn,
    "GET /api/detail-types": () => ({ body: [] }),
    "GET /api/project-types": () => ({ body: { types: [], stages: [] } }),
  });
  const view = render(<ExampleApp />);
  return { sent, view };
}

const lastTour = () => driven.configs[driven.configs.length - 1]!;

describe("the example project", () => {
  it("shows a fictional project without the page's own API, for a visitor", async () => {
    const { sent } = visit(false);
    expect(await screen.findByRole("heading", { level: 1, name: "Casa das Araucárias" })).toBeInTheDocument();
    expect(screen.getByText(/Projeto de exemplo: nada é salvo/)).toBeInTheDocument();
    expect(screen.getByText("Projeto Arquitetônico")).toBeInTheDocument();
    expect(screen.getByText("Apresentação do estudo")).toBeInTheDocument();
    // The current stage is open, with its files: an image, a PDF and a DWG.
    const current = document.getElementById("stage-2")!;
    expect(await within(current).findByText("Estudo de cobertura.jpg")).toBeVisible();
    expect(within(current).getByText("Implantação - estudo A.pdf")).toBeVisible();
    expect(within(current).getByText("Planta baixa - térreo.dwg")).toBeVisible();
    // A visitor: the client's view, no staff bar.
    expect(screen.queryByRole("navigation", { name: "Ferramentas do escritório" })).toBeNull();
    // Only who is signed in and the office were asked for; nothing about pages.
    expect(sent.map((r) => `${r.method} ${r.path}`).sort()).toEqual(["GET /api/me", "GET /api/tenant"]);
  });

  it("lets staff edit in memory: the page changes, no request leaves, and a new visit starts over", async () => {
    const { sent, view } = visit(true);
    await screen.findByRole("heading", { level: 1, name: "Casa das Araucárias" });
    expect(setupTour.startTour).not.toHaveBeenCalled(); // the example has its own tour
    expect(screen.getByRole("navigation", { name: "Ferramentas do escritório" })).toBeInTheDocument();
    await userEvent.click(await screen.findByRole("button", { name: "Editar" }));

    // A pencil: the description.
    await userEvent.click(await screen.findByRole("button", { name: "Editar descrição" }));
    const box = await screen.findByLabelText("Descrição");
    await userEvent.clear(box);
    await userEvent.type(box, "Uma casa só nossa.");
    await userEvent.click(screen.getByRole("button", { name: "Salvar" }));
    expect(await screen.findByText("Uma casa só nossa.")).toBeInTheDocument();

    // "Avançar": the next stage becomes the current one, and the bell tells the client.
    await userEvent.click(await screen.findByRole("button", { name: /Avançar para 04 Projeto 3D/ }));
    await waitFor(() =>
      expect(document.getElementById("stage-3")?.querySelector(".pill--current")).toHaveTextContent("Em andamento"),
    );

    // An upload to the open stage (03): it shows there, from this browser.
    const input = document.getElementById("up-3") as HTMLInputElement;
    await userEvent.upload(input, new File(["x"], "Croqui da sala.png", { type: "image/png" }));
    expect(await within(document.getElementById("stage-2")!).findByText("Croqui da sala.png")).toBeInTheDocument();

    // Nothing but reads ever reached the server.
    expect(sent.filter((r) => r.method !== "GET")).toEqual([]);
    expect(sent.every((r) => ["/api/me", "/api/tenant", "/api/detail-types", "/api/project-types"].includes(r.path))).toBe(
      true,
    );

    // Another visit: the example as it was.
    view.unmount();
    visit(true);
    await screen.findByRole("heading", { level: 1, name: "Casa das Araucárias" });
    expect(screen.queryByText("Uma casa só nossa.")).toBeNull();
    expect(screen.queryByText("Croqui da sala.png")).toBeNull();
  }, 15_000); // several edits, one after another

  it("hides a file from the client from its menu, in memory", async () => {
    const { sent } = visit(true);
    await userEvent.click(await screen.findByRole("button", { name: "Editar" }));
    const menu = await screen.findByRole("button", { name: /Estudo de cobertura\.jpg/, expanded: false });
    await userEvent.click(menu);
    await userEvent.click(await screen.findByRole("menuitem", { name: /Ocultar do cliente/ }));
    const stage = document.getElementById("stage-2")!;
    await waitFor(() => expect(within(stage).queryByText("Estudo de cobertura.jpg")).toBeNull());
    expect(sent.filter((r) => r.method !== "GET")).toEqual([]);
  });
});

describe("the explore tour", () => {
  it("starts on every visit, in the client's view, and ends pointing back to the painel", async () => {
    const { view } = visit(true);
    await screen.findByRole("heading", { level: 1, name: "Casa das Araucárias" });
    await waitFor(() => expect(driven.drive).toHaveBeenCalledTimes(1));
    const titles = lastTour().steps.map((s: { popover: { title: string } }) => s.popover.title);
    expect(titles).toEqual(
      expect.arrayContaining([
        "O nome e o tipo do projeto",
        "A descrição",
        "As informações",
        "A próxima reunião",
        "As etapas",
        "Os arquivos da etapa",
        "Atualizações",
        "Experimente editar",
      ]),
    );
    const end = lastTour().steps.at(-1);
    expect(end.popover.title).toBe("Agora, o seu projeto");
    expect(end.element).toBe('.dock a[href="/painel/"]'); // staff: the way back to Primeiros passos
    expect(document.querySelector(".client.editing")).toBeNull();

    // Closing it stores nothing; the next visit has it again.
    lastTour().onDestroyStarted();
    view.unmount();
    const again = visit(false);
    await screen.findByRole("heading", { level: 1, name: "Casa das Araucárias" });
    await waitFor(() => expect(driven.drive).toHaveBeenCalledTimes(2));
    expect(again.sent.some((r) => r.path === "/api/me/tour-seen")).toBe(false);
    // A visitor has no staff bar: the tour ends where it is.
    expect(lastTour().steps.at(-1).element).toBeUndefined();
    expect(lastTour().steps.some((s: { element?: string }) => s.element === '[data-tour="mode"]')).toBe(false);
  });

  it("can be skipped with “Pular”, and runs again from “?”", async () => {
    visit(true);
    await screen.findByRole("heading", { level: 1, name: "Casa das Araucárias" });
    await waitFor(() => expect(driven.drive).toHaveBeenCalledTimes(1));
    const footer = document.createElement("div");
    lastTour().onPopoverRender({ footer }, { state: { activeIndex: 0 } });
    await userEvent.click(within(footer).getByRole("button", { name: "Pular" }));
    expect(driven.destroy).toHaveBeenCalled();
    lastTour().onDestroyStarted(); // Driver.js's way out

    await userEvent.click(screen.getByRole("button", { name: "Ver o tour da página" }));
    await waitFor(() => expect(driven.drive).toHaveBeenCalledTimes(2));
    expect(setupTour.startTour).not.toHaveBeenCalled();
  });
});
