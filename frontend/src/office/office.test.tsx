import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { initials } from "../pages/SettingsOfficePage";
import * as imageCrop from "../ui/imageCrop";
import * as drawing from "./svgToPng";
import { fakeApi, ME, renderAt, TENANT } from "../test/render";

// The browser's image decoding and canvas aren't in the test DOM: a 500×500 image.
vi.mock("../ui/imageCrop", async (original) => ({
  ...(await original<typeof import("../ui/imageCrop")>()),
  loadImage: vi.fn(async () => ({ naturalWidth: 500, naturalHeight: 500 }) as HTMLImageElement),
  trimmed: vi.fn(() => ({ x: 0, y: 40, width: 100, height: 20 })),
  withoutBackground: vi.fn(async () => null),
  cropToFile: vi.fn(async (_image: unknown, _box: unknown, output: { type: string }, name: string) => new File(["x"], name, { type: output.type })),
}));

type Office = {
  name: string;
  contact_email: string | null;
  logo_url: string | null;
  logo_dark_url: string | null;
  logo_needs_png: boolean;
  can_manage: boolean;
};
const OFFICE: Office = {
  name: "Alinea",
  contact_email: null,
  logo_url: null,
  logo_dark_url: null,
  logo_needs_png: false,
  can_manage: true,
};
const LOCAL = { kind: "folder", writer_status: "none", reader_status: "unknown", account_email: null, folder_url: null, can_manage: true };
const NONE = { ...LOCAL, kind: null };

function api(office: Office = OFFICE, drive: object = LOCAL, me = ME, extra = {}) {
  return fakeApi({
    "GET /api/tenant": () => ({ body: TENANT }),
    "GET /api/me": () => ({ body: me }),
    "GET /api/office": () => ({ body: office }),
    "GET /api/drive": () => ({ body: drive }),
    "GET /api/onboarding": () => ({ body: { storage_connected: true, office_details: false, has_project: false } }),
    ...extra,
  });
}

afterEach(() => vi.unstubAllGlobals());

describe("Configurações → Escritório", () => {
  it("saves the name and contact email", async () => {
    const sent = api(OFFICE, LOCAL, ME, {
      "PATCH /api/office": (body: unknown) => ({ body: { ...OFFICE, ...(body as object) } }),
    });
    renderAt("/configuracoes");
    const name = await screen.findByLabelText(/Nome do escritório/);
    await userEvent.clear(name);
    await userEvent.type(name, "ALÍNEA ARQUITETOS");
    await userEvent.type(screen.getByLabelText(/E-mail de contato/), "contato@alinea.com.br");
    await userEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await waitFor(() => expect(sent.some((r) => r.method === "PATCH")).toBe(true));
    expect(sent.find((r) => r.method === "PATCH")?.body).toEqual({
      name: "ALÍNEA ARQUITETOS",
      contact_email: "contato@alinea.com.br",
    });
    expect(await screen.findByText("Salvo.")).toBeInTheDocument();
  });

  it("can be filled in from the first steps, without leaving the projects", async () => {
    const sent = api(OFFICE, LOCAL, ME, {
      "PATCH /api/office": (body: unknown) => ({ body: { ...OFFICE, ...(body as object) } }),
    });
    renderAt("/");
    const steps = await screen.findByRole("region", { name: "Primeiros passos" });
    await userEvent.click(within(steps).getByRole("button", { name: "Personalizar" }));
    const dialog = await screen.findByRole("dialog", { name: "Dados do escritório" });
    await userEvent.type(within(dialog).getByLabelText(/E-mail de contato/), "contato@alinea.com.br");
    await userEvent.click(within(dialog).getByRole("button", { name: "Salvar" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull()); // saved: it closes
    expect(sent.find((r) => r.method === "PATCH")?.body).toEqual({ name: "Alinea", contact_email: "contato@alinea.com.br" });
    expect(await screen.findByText("Salvo.")).toBeInTheDocument();
  });

  it("limits the name to 28 characters, counting as you type", async () => {
    api();
    renderAt("/configuracoes");
    const name = await screen.findByLabelText(/Nome do escritório/);
    expect(name).toHaveAttribute("maxLength", "28");
    await userEvent.clear(name);
    await userEvent.type(name, "Studio Alínea");
    expect(screen.getByText("13/28")).toBeInTheDocument();
  });

  it("shows a refused email in Portuguese", async () => {
    api(OFFICE, LOCAL, ME, {
      "PATCH /api/office": () => ({ status: 422, body: { error: "invalid_email" } }),
    });
    renderAt("/configuracoes/escritorio");
    await userEvent.type(await screen.findByLabelText(/E-mail de contato/), "x@y");
    await userEvent.click(screen.getByRole("button", { name: "Salvar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Informe um e-mail válido");
  });

  it("uploads a logo as a file, with the CSRF token", async () => {
    const sent = api(OFFICE, LOCAL, ME, {
      "PUT /api/office/logo": () => ({ body: { ...OFFICE, logo_url: "/api/office/logo?v=1" } }),
    });
    renderAt("/configuracoes/escritorio");
    await screen.findByRole("button", { name: "Escolher imagem" }); // once Drive's state is known
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await userEvent.upload(input, new File(["png"], "logo.png", { type: "image/png" }));
    // Cropped first: its empty margins already trimmed, then sent as a PNG.
    const crop = await screen.findByRole("dialog", { name: "Ajustar o logo" });
    expect(imageCrop.trimmed).toHaveBeenCalled();
    await userEvent.click(await within(crop).findByRole("button", { name: "Usar recorte" }));
    await waitFor(() => expect(sent.some((r) => r.path === "/api/office/logo")).toBe(true));
    expect(imageCrop.cropToFile).toHaveBeenCalledWith(expect.anything(), expect.anything(), imageCrop.LOGO_OUTPUT, "logo.png");
    const request = sent.find((r) => r.path === "/api/office/logo");
    expect(request?.headers.get("Content-Type")).toMatch(/^multipart\/form-data/);
    expect(request?.headers.get("X-CSRF-Token")).toBe("csrf-123");
    expect(await screen.findByRole("img", { name: "Logo de Alinea" })).toHaveAttribute(
      "src",
      "/api/office/logo?v=1",
    );
  });

  it("shows the uploaded logo in the header instead of the office's name", async () => {
    api({ ...OFFICE, logo_url: "/api/office/logo?v=7" } as unknown as typeof OFFICE);
    renderAt("/");
    const header = await screen.findByRole("banner");
    const logo = await within(header).findByRole("img", { name: "Alinea" }); // the name, for screen readers
    expect(logo).toHaveAttribute("src", "/api/office/logo?v=7");
    expect(header).not.toHaveTextContent("Alinea"); // not written out a second time
  });

  it("shows the office's name in the header until there is a logo", async () => {
    api();
    renderAt("/");
    const header = await screen.findByRole("banner");
    expect(header).toHaveTextContent("Alinea");
    expect(within(header).queryByRole("img")).not.toBeInTheDocument();
  });

  it("shows the office's initials in an empty slot until there is a logo", async () => {
    api({ ...OFFICE, name: "ALINEA ARQUITETOS" });
    renderAt("/configuracoes/escritorio");
    const slot = await screen.findByRole("img", { name: "Nenhum logo ainda." });
    expect(slot).toHaveTextContent("AA");
  });

  it("says first that the logo needs Google Drive, with the way to connect it", async () => {
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign, origin: window.location.origin });
    api(OFFICE, NONE, ME, {
      "POST /api/drive/connect": () => ({ body: { url: "https://accounts.google.com/o/oauth2/v2/auth?x" } }),
    });
    renderAt("/configuracoes/escritorio");
    const warning = await screen.findByText(/Para enviar o logo, conecte primeiro o Google Drive/);
    // No empty slot or file specs for a logo that can't go up yet.
    expect(screen.queryByText(/PNG, JPG, WebP ou SVG/)).toBeNull();
    expect(screen.queryByRole("img", { name: "Nenhum logo ainda." })).toBeNull();
    expect(screen.queryByRole("button", { name: "Escolher imagem" })).toBeNull();
    await userEvent.click(within(warning.parentElement!).getByRole("button", { name: "Conectar Google Drive" }));
    await waitFor(() => expect(assign).toHaveBeenCalledWith("https://accounts.google.com/o/oauth2/v2/auth?x"));
  });

  it("says so, with the support code, when the Drive status can't be loaded", async () => {
    fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/me": () => ({ body: ME }),
      "GET /api/office": () => ({ body: OFFICE }),
      "GET /api/drive": () => ({ status: 500, body: {}, headers: { "X-Request-ID": "req8" } }),
      "GET /api/onboarding": () => ({ body: { storage_connected: true, office_details: false, has_project: false } }),
    });
    renderAt("/configuracoes/escritorio");
    expect(await screen.findByRole("alert", {}, { timeout: 4000 })).toHaveTextContent("req8");
  });

  it("offers to reconnect an expired connection", async () => {
    api(OFFICE, { ...LOCAL, kind: "google", writer_status: "expired", reader_status: "ok" });
    renderAt("/configuracoes/escritorio");
    expect(await screen.findByRole("button", { name: "Reconectar" })).toBeInTheDocument();
  });

  it("sends to the Drive settings while the portal cannot read the folder", async () => {
    api(OFFICE, { ...LOCAL, kind: "google", writer_status: "connected", reader_status: "no_access" });
    renderAt("/configuracoes/escritorio");
    const warning = await screen.findByText(/O portal não consegue ler a pasta do escritório/);
    expect(within(warning.parentElement!).getByRole("link", { name: "Google Drive" })).toHaveAttribute(
      "href",
      "/configuracoes/drive",
    );
  });

  it("is read-only for members", async () => {
    api({ ...OFFICE, can_manage: false }, LOCAL, { ...ME, role: "member" });
    renderAt("/configuracoes/escritorio");
    expect(await screen.findByText(/Só o responsável pelo escritório pode alterar/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Salvar" })).toBeNull();
  });
});

describe("the logo's crop and dark mode", () => {
  const WITH_LOGO = { ...OFFICE, logo_url: "/api/office/logo?v=1" };

  /** The latest "Escolher imagem…" on the page: the dark mode one comes after. */
  async function choose(button: string) {
    expect(screen.getByRole("button", { name: button })).toBeInTheDocument();
    const input = [...document.querySelectorAll<HTMLInputElement>('input[type="file"]')].at(-1)!;
    await userEvent.upload(input, new File(["png"], "logo.png", { type: "image/png" }));
  }

  it("offers to remove a plain background, and only then", async () => {
    vi.mocked(imageCrop.withoutBackground).mockResolvedValueOnce("blob:clean");
    api();
    renderAt("/configuracoes/escritorio");
    await screen.findByRole("button", { name: "Escolher imagem" });
    await choose("Escolher imagem");
    const crop = await screen.findByRole("dialog", { name: "Ajustar o logo" });
    expect(await within(crop).findByRole("checkbox", { name: "Remover fundo" })).not.toBeChecked();
    await userEvent.click(within(crop).getByRole("button", { name: "Cancelar" }));

    await choose("Escolher imagem"); // a transparent one: nothing to remove
    const again = await screen.findByRole("dialog", { name: "Ajustar o logo" });
    await within(again).findByRole("button", { name: "Usar recorte" });
    expect(within(again).queryByRole("checkbox", { name: "Remover fundo" })).toBeNull();
  });

  it("uses the same logo in dark mode until another is chosen", async () => {
    const sent = api(WITH_LOGO, LOCAL, ME, {
      "PUT /api/office/logo/dark": () => ({ body: { ...WITH_LOGO, logo_dark_url: "/api/office/logo?dark=true&v=2" } }),
    });
    renderAt("/configuracoes/escritorio");
    const same = await screen.findByRole("checkbox", { name: "Usar o mesmo logo no modo escuro" });
    expect(same).toBeChecked();
    expect(screen.queryByRole("button", { name: "Escolher imagem para o modo escuro" })).toBeNull();
    await userEvent.click(same);
    await choose("Escolher imagem para o modo escuro");
    const crop = await screen.findByRole("dialog", { name: "Ajustar o logo do modo escuro" });
    await userEvent.click(await within(crop).findByRole("button", { name: "Usar recorte" }));
    await waitFor(() => expect(sent.some((r) => r.method === "PUT" && r.path === "/api/office/logo/dark")).toBe(true));
    expect(await screen.findByText("Logo do modo escuro atualizado.")).toBeInTheDocument();
  });

  it("goes back to one logo, removing the dark mode one", async () => {
    const both = { ...WITH_LOGO, logo_dark_url: "/api/office/logo?dark=true&v=2" };
    const sent = api(both, LOCAL, ME, { "DELETE /api/office/logo/dark": () => ({ body: WITH_LOGO }) });
    renderAt("/configuracoes/escritorio");
    const same = await screen.findByRole("checkbox", { name: "Usar o mesmo logo no modo escuro" });
    expect(same).not.toBeChecked();
    await userEvent.click(same);
    await waitFor(() => expect(sent.some((r) => r.method === "DELETE" && r.path === "/api/office/logo/dark")).toBe(true));
    expect(await screen.findByText("O modo escuro usa o mesmo logo.")).toBeInTheDocument();
  });
});

describe("initials", () => {
  it("takes the first letters of the first two words, ignoring parentheses", () => {
    expect(initials("ALINEA ARQUITETOS")).toBe("AA");
    expect(initials("Estúdio Norte (dev)")).toBe("EN");
    expect(initials("ateliê")).toBe("A");
  });
});


describe("an SVG logo's PNG, for emails (A32)", () => {
  it("gives an older SVG logo its PNG when an owner opens the painel", async () => {
    vi.spyOn(drawing, "svgToPng").mockResolvedValue(new Blob(["png"], { type: "image/png" }));
    const needs = { ...OFFICE, logo_url: "/api/office/logo?v=1", logo_needs_png: true };
    const sent = api(needs, LOCAL, ME, {
      "GET /api/office/logo": () => ({ body: "<svg/>" }),
      "PUT /api/office/logo/png": () => ({ body: { ...needs, logo_needs_png: false } }),
    });
    renderAt("/");
    await waitFor(() => expect(sent.some((r) => r.path === "/api/office/logo/png")).toBe(true));
    expect(sent.filter((r) => r.path === "/api/office/logo/png")).toHaveLength(1); // once
  });

  it("leaves it to an owner", async () => {
    const draw = vi.spyOn(drawing, "svgToPng");
    const needs = { ...OFFICE, logo_url: "/api/office/logo?v=1", logo_needs_png: true, can_manage: false };
    const sent = api(needs);
    renderAt("/");
    await screen.findByRole("heading", { name: "Projetos" }).catch(() => undefined);
    expect(sent.some((r) => r.path === "/api/office/logo/png")).toBe(false);
    expect(draw).not.toHaveBeenCalled();
  });
});
