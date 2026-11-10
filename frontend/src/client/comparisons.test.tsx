// Before-and-after comparisons (A46): the slider, the card and its viewer, and in
// edit mode the "+" card's dialog and a comparison's "⋯".
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import i18next from "i18next";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fakeApi, TENANT } from "../test/render";
import { BeforeAfter } from "../ui/BeforeAfter";
import { ClientApp } from "./ClientApp";
import type { Page } from "./format";
import { entriesFor } from "./Updates";

vi.mock("./Tour", () => ({ startTour: vi.fn() }));

const PAGE: Page = {
  id: "6f1c1d1e-0000-4000-8000-0000000000b1",
  office: { name: "Alinea", logo_url: null, logo_dark_url: null },
  team: [],
  locale: "pt-BR",
  timezone: "America/Sao_Paulo",
  name: "Casa Jardim",
  client_name: "Família Oliveira",
  project_type: "Reforma",
  project_type_key: "renovation",
  description: "",
  cover_url: null,
  features: [],
  completed: false,
  archived: false,
  current_position: null,
  last_update: "2026-11-01T12:00:00Z",
  details: [],
  stages: [
    { position: 1, title: "Briefing", about: null, notes: "", completed: false },
    { position: 2, title: "Obra", about: null, notes: "", completed: false },
  ],
  next_meeting: null,
  in_proposal: false,
  proposal: null,
  proposal_url: null,
};

const image = (key: string, name: string) => ({
  key,
  name,
  kind: "image",
  size: 1000,
  modified_at: "2026-11-01T12:00:00Z",
  older: [],
});

const KITCHEN = {
  ...image("k-before", "Cozinha"),
  comparison: {
    after: image("k-after", "Cozinha (depois - Obra).jpg"),
    before_label: null,
    after_label: "Obra",
    before_name: "Cozinha (antes).jpg",
    after_name: "Cozinha (depois - Obra).jpg",
  },
};

const FILES = {
  stages: [
    { position: 1, groups: [{ folder: null, files: [KITCHEN] }] },
    { position: 2, groups: [] },
  ],
};

beforeEach(() => {
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:chosen"), revokeObjectURL: vi.fn() }));
});
afterEach(() => vi.unstubAllGlobals());

describe("the slider", () => {
  it("moves by the arrow keys, Home and End, and says how much of each side shows", async () => {
    render(
      <BeforeAfter title="Cozinha" before={{ src: "a.jpg", label: "Antes" }} after={{ src: "b.jpg", label: "Obra" }} />,
    );
    const slider = screen.getByRole("slider", { name: "Comparação antes e depois: Cozinha" });
    expect(slider).toHaveAttribute("aria-valuenow", "50");
    slider.focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(slider).toHaveAttribute("aria-valuenow", "55");
    await userEvent.keyboard("{Shift>}{ArrowLeft}{/Shift}");
    expect(slider).toHaveAttribute("aria-valuenow", "35");
    expect(slider).toHaveAttribute("aria-valuetext", "35% de “Antes”, o restante de “Obra”");
    await userEvent.keyboard("{End}");
    expect(slider).toHaveAttribute("aria-valuenow", "100");
    await userEvent.keyboard("{ArrowRight}");
    expect(slider).toHaveAttribute("aria-valuenow", "100"); // never past the edge
    await userEvent.keyboard("{Home}");
    expect(slider).toHaveAttribute("aria-valuenow", "0");
  });

  it("follows the pointer from where it is pressed, while it is held", () => {
    render(<BeforeAfter title="Cozinha" before={{ src: "a.jpg", label: "Antes" }} after={{ src: "b.jpg", label: "Depois" }} />);
    const slider = screen.getByRole("slider");
    const frame = slider.parentElement!;
    vi.spyOn(frame, "getBoundingClientRect").mockReturnValue(DOMRect.fromRect({ x: 100, y: 0, width: 400, height: 300 }));
    let held = false;
    Object.assign(frame, {
      setPointerCapture: () => (held = true),
      hasPointerCapture: () => held,
    });
    fireEvent.pointerMove(frame, { clientX: 200 }); // not pressed: nothing
    expect(slider).toHaveAttribute("aria-valuenow", "50");
    fireEvent.pointerDown(frame, { clientX: 200, button: 0, pointerId: 1 });
    expect(slider).toHaveAttribute("aria-valuenow", "25");
    fireEvent.pointerMove(frame, { clientX: 700, pointerId: 1 }); // past the right edge
    expect(slider).toHaveAttribute("aria-valuenow", "100");
  });

  it("shows each side's label over its image", () => {
    render(<BeforeAfter title="Sala" before={{ src: "a.jpg", label: "Projeto" }} after={{ src: "b.jpg", label: "Obra" }} />);
    expect(screen.getByText("Projeto")).toHaveAttribute("data-side", "before");
    expect(screen.getByText("Obra")).toHaveAttribute("data-side", "after");
  });
});

describe("a comparison on the page", () => {
  function asClient(extra: Parameters<typeof fakeApi>[0] = {}) {
    window.history.pushState({}, "", "/casa-jardim");
    const sent = fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/pages/casa-jardim": () => ({ body: PAGE }),
      "GET /api/pages/casa-jardim/files": () => ({ body: FILES }),
      ...extra,
    });
    render(<ClientApp />);
    return sent;
  }

  it("is one card that opens on the slider, with each image to download by its label", async () => {
    asClient();
    const card = (await screen.findByRole("button", { name: "Abrir Cozinha" })).closest(".file") as HTMLElement;
    expect(within(card).getByText("Antes e depois")).toBeInTheDocument();
    await userEvent.click(within(card).getByRole("button", { name: "Abrir Cozinha" }));
    const viewer = await screen.findByRole("dialog", { name: "Cozinha" });
    expect(within(viewer).getByRole("slider", { name: "Comparação antes e depois: Cozinha" })).toBeInTheDocument();
    expect(within(viewer).getByText("Antes")).toBeInTheDocument();
    expect(within(viewer).getByText("Obra")).toBeInTheDocument(); // its own label
    expect(within(viewer).getByRole("link", { name: "Baixar “Antes”" })).toHaveAttribute(
      "href",
      "/api/pages/casa-jardim/files/k-before",
    );
    expect(within(viewer).getByRole("link", { name: "Baixar “Obra”" })).toHaveAttribute(
      "href",
      "/api/pages/casa-jardim/files/k-after",
    );
  });

  it("lists each image's versions under its label, the after image's older ones too", async () => {
    window.history.pushState({}, "", "/casa-jardim");
    const after = { ...KITCHEN.comparison.after, version: 2, older: [{ ...image("k-after-1", "Cozinha (depois - Obra).jpg"), version: 1 }] };
    fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/pages/casa-jardim": () => ({ body: PAGE }),
      "GET /api/pages/casa-jardim/files": () => ({
        body: { stages: [{ position: 1, groups: [{ folder: null, files: [{ ...KITCHEN, comparison: { ...KITCHEN.comparison, after } }] }] }] },
      }),
    });
    render(<ClientApp />);
    await userEvent.click(await screen.findByRole("button", { name: "3 versões" }));
    const dialog = await screen.findByRole("dialog", { name: "Cozinha" });
    const obra = within(dialog).getByRole("region", { name: "Obra" });
    expect(within(obra).getByRole("link", { name: "Baixar a versão 1 de Cozinha (depois - Obra).jpg" })).toHaveAttribute(
      "href",
      "/api/pages/casa-jardim/files/k-after-1",
    );
    expect(within(within(dialog).getByRole("region", { name: "Antes" })).getAllByRole("listitem")).toHaveLength(1);
  });

  it("shares both its images when its card is picked to share", async () => {
    const sent = asClient({
      "POST /api/pages/casa-jardim/shares": () => ({
        status: 201,
        body: { link: { id: "l1", files: 2 }, url: "http://alinea.localhost/share/tok", owner: "own-1" },
      }),
    });
    await userEvent.click(await screen.findByRole("button", { name: "Compartilhar arquivos de Briefing" }));
    const dialog = await screen.findByRole("dialog", { name: "Compartilhar arquivos" });
    expect(within(dialog).getByRole("checkbox", { name: /Cozinha/ })).toBeChecked();
    expect(within(dialog).getByText("2 KB")).toBeInTheDocument(); // both images' size
    await userEvent.click(within(dialog).getByRole("button", { name: "Gerar link" }));
    await waitFor(() =>
      expect(sent.find((r) => r.path.endsWith("/shares"))?.body).toMatchObject({ files: ["k-before", "k-after"] }),
    );
  });

  it("names a new comparison once in the updates, by its title", () => {
    const t = i18next.t.bind(i18next) as (key: string, values?: Record<string, unknown>) => string;
    const [entry] = entriesFor(
      PAGE,
      [{ id: "u1", kind: "file_published", occurred_at: "2026-11-01T12:00:00Z", stage_position: 1, name: "Cozinha", comparison: true }],
      t,
      "pt-BR",
    );
    expect(entry!.title).toBe("Comparação antes e depois: Cozinha");
  });
});

describe("comparisons in edit mode", () => {
  class FakeXhr {
    static sent: { url: string; body: File }[] = [];
    static refused = new Set<string>(); // addresses Google refuses (403)
    upload: { onprogress?: (event: { loaded: number }) => void } = {};
    status = 0;
    responseText = "";
    onload?: () => void;
    private url = "";
    open(_method: string, url: string) {
      this.url = url;
    }
    setRequestHeader() {}
    getResponseHeader() {
      return null;
    }
    send(body: File) {
      FakeXhr.sent.push({ url: this.url, body });
      this.upload.onprogress?.({ loaded: body.size });
      this.status = FakeXhr.refused.has(this.url) ? 403 : 200;
      setTimeout(() => this.onload?.());
    }
  }

  function asStaff(extra: Parameters<typeof fakeApi>[0] = {}) {
    FakeXhr.sent = [];
    FakeXhr.refused = new Set();
    vi.stubGlobal("XMLHttpRequest", FakeXhr);
    window.history.pushState({}, "", "/casa-jardim");
    const sent = fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/me": () => ({ body: { name: "Ana", email: "ana@alinea.example", csrf_token: "csrf-9" } }),
      "GET /api/pages/casa-jardim": () => ({
        // Comparisons are switched on for the office (A40).
        body: { ...PAGE, features: ["before_after"], staff: { project_id: "p-1", status: "active", row_version: 4 } },
      }),
      "GET /api/pages/casa-jardim/files": () => ({ body: FILES }),
      ...extra,
    });
    render(<ClientApp />);
    return sent;
  }

  async function startEditing() {
    const bar = await screen.findByRole("navigation", { name: "Ferramentas do escritório" });
    await waitFor(() => expect(within(bar).getByRole("button", { name: "Editar" })).toBeEnabled());
    await userEvent.click(within(bar).getByRole("button", { name: "Editar" }));
  }

  async function openNewComparison(stage: string) {
    const region = await screen.findByRole("region", { name: stage });
    await userEvent.click(await within(region).findByRole("button", { name: "Adicionar à etapa" }));
    await userEvent.click(within(region).getByRole("menuitem", { name: /Comparação antes e depois/ }));
    return screen.findByRole("dialog", { name: "Comparação antes e depois" });
  }

  it("uploads two images named for a comparison, from the stage's \"+\" card", async () => {
    const sent = asStaff({
      "POST /api/projects/p-1/stages/1/comparisons": () => ({
        body: { before_url: "https://upload.example/b", after_url: "https://upload.example/a" },
      }),
    });
    await startEditing();
    const dialog = await openNewComparison("Briefing");
    const before = new File(["b"], "Sala atual.jpg", { type: "image/jpeg" });
    const after = new File(["aa"], "render.png", { type: "image/png" });
    await userEvent.upload(within(dialog).getByLabelText("Escolher a imagem “Antes”"), before);
    await userEvent.upload(within(dialog).getByLabelText("Escolher a imagem “Depois”"), after);
    // The first image's name until another is typed.
    expect(within(dialog).getByRole("textbox", { name: "Nome da comparação" })).toHaveValue("Sala atual");
    // A label is renamed from its pencil, on its image; Enter keeps it without sending.
    expect(within(dialog).queryByRole("textbox", { name: "Rótulo de “Depois”" })).not.toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Renomear “Depois”" }));
    await userEvent.type(within(dialog).getByRole("textbox", { name: "Rótulo de “Depois”" }), "Obra pronta{Enter}");
    expect(within(dialog).getByRole("button", { name: "Renomear “Obra pronta”" })).toHaveFocus();
    expect(sent.some((r) => r.path.endsWith("/comparisons"))).toBe(false);
    await userEvent.click(within(dialog).getByRole("button", { name: "Enviar comparação" }));
    expect(await screen.findByText("Comparação “Sala atual” enviada.")).toBeInTheDocument();
    expect(sent.find((r) => r.path.endsWith("/comparisons"))?.body).toEqual({
      row_version: 4,
      title: "Sala atual",
      before: { name: "Sala atual.jpg", size: 1, mime_type: "image/jpeg" },
      after: { name: "render.png", size: 2, mime_type: "image/png" },
      after_label: "Obra pronta",
    });
    expect(FakeXhr.sent.map((s) => [s.url, s.body.name]).sort()).toEqual([
      ["https://upload.example/a", "render.png"],
      ["https://upload.example/b", "Sala atual.jpg"],
    ]);
  });

  it("after one image went up and the other didn't, tries again with the missing one only", async () => {
    let tries = 0;
    let release = () => {};
    const sent = asStaff({
      "POST /api/projects/p-1/stages/1/comparisons": () => {
        tries += 1;
        return tries === 1
          ? // Held until the test has looked at the dialog while it sends.
            new Promise((answer) => {
              release = () => answer({ body: { before_url: "https://upload.example/b", after_url: "https://upload.example/a" } });
            })
          : { body: { before_url: null, after_url: "https://upload.example/a2" } };
      },
      "POST /api/projects/p-1/stages/1/uploads/failed": () => ({ status: 502, body: { error: "upload_failed" } }),
    });
    await startEditing();
    const dialog = await openNewComparison("Briefing");
    await userEvent.upload(within(dialog).getByLabelText("Escolher a imagem “Antes”"), new File(["b"], "Sala.jpg", { type: "image/jpeg" }));
    await userEvent.upload(within(dialog).getByLabelText("Escolher a imagem “Depois”"), new File(["a"], "Render.jpg", { type: "image/jpeg" }));
    FakeXhr.refused.add("https://upload.example/a"); // the "after" upload is refused for good
    vi.useFakeTimers({ shouldAdvanceTime: true }); // sendFile's waits before giving up
    await userEvent.click(within(dialog).getByRole("button", { name: "Enviar comparação" }));
    // While the images go up, nothing that names them can change.
    expect(within(dialog).getByRole("textbox", { name: "Nome da comparação" })).toBeDisabled();
    expect(within(dialog).getByRole("button", { name: "Renomear “Depois”" })).toBeDisabled();
    release();
    await waitFor(() => expect(sent.some((r) => r.path.endsWith("/uploads/failed"))).toBe(true));
    vi.useRealTimers();
    // The "before" went up: it stays as it is, and so does the name its file has.
    await waitFor(() => expect(within(dialog).getByText("Já enviada")).toBeInTheDocument());
    // The files aren't listed again meanwhile: the list changing shape would close the dialog.
    const listings = () => sent.filter((r) => r.method === "GET" && r.path === "/api/pages/casa-jardim/files").length;
    const before = listings();
    expect(within(dialog).getByRole("textbox", { name: "Nome da comparação" })).toBeDisabled();
    await userEvent.click(within(dialog).getByRole("button", { name: "Enviar comparação" }));
    expect(await screen.findByText("Comparação “Sala” enviada.")).toBeInTheDocument();
    expect(before).toBe(1); // only the page's first listing, until the comparison was whole
    const retry = sent.filter((r) => r.path.endsWith("/comparisons"))[1]!.body as Record<string, unknown>;
    expect(retry.before).toBeUndefined();
    expect(retry.after).toEqual({ name: "Render.jpg", size: 1, mime_type: "image/jpeg" });
    expect(FakeXhr.sent.at(-1)?.url).toBe("https://upload.example/a2");
  });

  it("lists the files again when the dialog is closed after only one image went up", async () => {
    const sent = asStaff({
      "POST /api/projects/p-1/stages/1/comparisons": () => ({
        body: { before_url: "https://upload.example/b", after_url: "https://upload.example/a" },
      }),
      "POST /api/projects/p-1/stages/1/uploads/failed": () => ({ status: 502, body: { error: "upload_failed" } }),
    });
    await startEditing();
    const dialog = await openNewComparison("Briefing");
    await userEvent.upload(within(dialog).getByLabelText("Escolher a imagem “Antes”"), new File(["b"], "Sala.jpg", { type: "image/jpeg" }));
    await userEvent.upload(within(dialog).getByLabelText("Escolher a imagem “Depois”"), new File(["a"], "Render.jpg", { type: "image/jpeg" }));
    FakeXhr.refused.add("https://upload.example/a");
    await userEvent.click(within(dialog).getByRole("button", { name: "Enviar comparação" }));
    await waitFor(() => expect(within(dialog).getByText("Já enviada")).toBeInTheDocument());
    const listings = () => sent.filter((r) => r.method === "GET" && r.path === "/api/pages/casa-jardim/files").length;
    expect(listings()).toBe(1);
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancelar" }));
    await waitFor(() => expect(listings()).toBe(2)); // the "before" now shows on its own
  });

  it("keeps a label as it was when its renaming is left with Escape, and the dialog open", async () => {
    asStaff();
    await startEditing();
    const dialog = await openNewComparison("Briefing");
    await userEvent.click(within(dialog).getByRole("button", { name: "Renomear “Antes”" }));
    await userEvent.type(within(dialog).getByRole("textbox", { name: "Rótulo de “Antes”" }), "Projeto{Escape}");
    expect(within(dialog).getByRole("button", { name: "Renomear “Antes”" })).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "Comparação antes e depois" })).toBeInTheDocument();
  });

  it("refuses a file that isn't a JPG, PNG, WebP or GIF before anything is sent", async () => {
    const sent = asStaff();
    await startEditing();
    const dialog = await openNewComparison("Briefing");
    await userEvent.upload(
      within(dialog).getByLabelText("Escolher a imagem “Antes”"),
      new File(["%PDF"], "Planta.pdf", { type: "application/pdf" }),
      { applyAccept: false },
    );
    expect(within(dialog).getByRole("alert")).toHaveTextContent("Escolha imagens JPG, PNG, WebP ou GIF para a comparação.");
    expect(within(dialog).getByRole("button", { name: "Enviar comparação" })).toBeDisabled();
    expect(sent.some((r) => r.path.endsWith("/comparisons"))).toBe(false);
  });

  it("shows no \"+\" card when comparisons are switched off for the office", async () => {
    asStaff({
      "GET /api/pages/casa-jardim": () => ({
        body: { ...PAGE, staff: { project_id: "p-1", status: "active", row_version: 4 } },
      }),
    });
    await startEditing();
    const region = await screen.findByRole("region", { name: "Briefing" });
    await within(region).findByLabelText("escolha no computador"); // the drop area, as before
    expect(within(region).queryByRole("button", { name: "Adicionar à etapa" })).not.toBeInTheDocument();
  });

  it("offers the stage's own file chooser from the \"+\" card too", async () => {
    asStaff();
    await startEditing();
    const region = await screen.findByRole("region", { name: "Briefing" });
    const chooser = (await within(region).findByLabelText("escolha no computador")) as HTMLInputElement;
    const opened = vi.spyOn(chooser, "click");
    await userEvent.click(await within(region).findByRole("button", { name: "Adicionar à etapa" }));
    await userEvent.click(within(region).getByRole("menuitem", { name: /Enviar arquivos/ }));
    expect(opened).toHaveBeenCalledTimes(1);
  });

  async function comparisonMenu() {
    const region = await screen.findByRole("region", { name: "Briefing" });
    await userEvent.click(await within(region).findByRole("button", { name: "Ações para Cozinha" }));
    return within(region).getByRole("menu");
  }

  it("renames a comparison and its labels from its \"⋯\"", async () => {
    const sent = asStaff({ "POST /api/pages/casa-jardim/comparisons/k-before/edit": () => ({ status: 204 }) });
    await startEditing();
    await userEvent.click(within(await comparisonMenu()).getByRole("menuitem", { name: /Editar comparação/ }));
    const dialog = await screen.findByRole("dialog", { name: "Editar comparação" });
    const title = within(dialog).getByRole("textbox", { name: "Nome da comparação" });
    await userEvent.clear(title);
    await userEvent.type(title, "Copa");
    await userEvent.type(within(dialog).getByRole("textbox", { name: "Rótulo de “Antes” (opcional)" }), "Projeto");
    await userEvent.click(within(dialog).getByRole("button", { name: "Salvar" }));
    expect(await screen.findByText("Comparação “Copa” atualizada.")).toBeInTheDocument();
    expect(sent.find((r) => r.path.endsWith("/edit"))?.body).toEqual({
      title: "Copa",
      before_label: "Projeto",
      after_label: "Obra",
    });
  });

  it("hides both images, and moves both, as one", async () => {
    const sent = asStaff({
      "POST /api/pages/casa-jardim/comparisons/k-before/hide": () => ({ status: 204 }),
      "POST /api/pages/casa-jardim/comparisons/k-before/move": () => ({ status: 204 }),
    });
    await startEditing();
    await userEvent.click(within(await comparisonMenu()).getByRole("menuitem", { name: /Ocultar do cliente/ }));
    await waitFor(() => expect(sent.some((r) => r.path.endsWith("/k-before/hide"))).toBe(true));
    await userEvent.click(within(await comparisonMenu()).getByRole("menuitem", { name: "Mover para…" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "02 Obra" }));
    await waitFor(() =>
      expect(sent.find((r) => r.path.endsWith("/k-before/move"))?.body).toEqual({ position: 2, row_version: 4 }),
    );
  });

  it("sends a new version of either side as that image's next version", async () => {
    const sent = asStaff({
      "POST /api/projects/p-1/stages/1/uploads": () => ({ body: { upload_url: "https://upload.example/v" } }),
    });
    await startEditing();
    const menu = await comparisonMenu();
    await userEvent.click(within(menu).getByRole("menuitem", { name: "Enviar nova versão de “Obra”" }));
    const region = screen.getByRole("region", { name: "Briefing" });
    const chooser = within(region).getByLabelText("Enviar nova versão de “Obra”") as HTMLInputElement;
    await waitFor(() => expect(chooser.accept).toBe(".jpg"));
    await userEvent.upload(chooser, new File(["v2"], "nova.jpg", { type: "image/jpeg" }));
    await waitFor(() =>
      expect(sent.find((r) => r.path.endsWith("/uploads"))?.body).toMatchObject({ name: "nova.jpg", version_of: "k-after" }),
    );
  });

});
