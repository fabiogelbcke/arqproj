import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { initials } from "../pages/SettingsOfficePage";
import * as drawing from "./svgToPng";
import { fakeApi, ME, renderAt, TENANT } from "../test/render";

type Office = {
  name: string;
  contact_email: string | null;
  logo_url: string | null;
  logo_needs_png: boolean;
  can_manage: boolean;
};
const OFFICE: Office = { name: "Alinea", contact_email: null, logo_url: null, logo_needs_png: false, can_manage: true };
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
    await waitFor(() => expect(sent.some((r) => r.path === "/api/office/logo")).toBe(true));
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

  it("explains that the logo waits for Google Drive", async () => {
    api(OFFICE, NONE);
    renderAt("/configuracoes/escritorio");
    expect(await screen.findByText(/Conecte o Google Drive para enviar o logo/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Escolher imagem" })).toBeNull();
  });

  it("waits while the portal cannot read the Drive folder", async () => {
    api(OFFICE, { ...LOCAL, kind: "google", writer_status: "connected", reader_status: "no_access" });
    renderAt("/configuracoes/escritorio");
    expect(await screen.findByText(/Conecte o Google Drive para enviar o logo/)).toBeInTheDocument();
  });

  it("is read-only for members", async () => {
    api({ ...OFFICE, can_manage: false }, LOCAL, { ...ME, role: "member" });
    renderAt("/configuracoes/escritorio");
    expect(await screen.findByText(/Só o responsável pelo escritório pode alterar/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Salvar" })).toBeNull();
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
  /** The multipart parts' names sent to `path` (fakeApi reads only JSON). */
  function formsTo(path: string) {
    const forms: string[][] = [];
    const inner = globalThis.fetch;
    vi.stubGlobal("fetch", async (input: Request) => {
      if (new URL(input.url).pathname === path) {
        const raw = await input.clone().text();
        forms.push([...raw.matchAll(/; name="([^"]+)"/g)].map((m) => m[1]!));
      }
      return inner(input);
    });
    return forms;
  }

  it("uploads an SVG logo with a PNG of it drawn in the browser", async () => {
    vi.spyOn(drawing, "svgToPng").mockResolvedValue(new Blob(["png"], { type: "image/png" }));
    api(OFFICE, LOCAL, ME, {
      "PUT /api/office/logo": () => ({ body: { ...OFFICE, logo_url: "/api/office/logo?v=1" } }),
    });
    const forms = formsTo("/api/office/logo");
    renderAt("/configuracoes/escritorio");
    await screen.findByRole("button", { name: "Escolher imagem" });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await userEvent.upload(input, new File(["<svg/>"], "logo.svg", { type: "image/svg+xml" }));
    await waitFor(() => expect(forms).toEqual([["file", "png"]]));
  });

  it("uploads other images as they are", async () => {
    const draw = vi.spyOn(drawing, "svgToPng");
    api(OFFICE, LOCAL, ME, { "PUT /api/office/logo": () => ({ body: OFFICE }) });
    const forms = formsTo("/api/office/logo");
    renderAt("/configuracoes/escritorio");
    await screen.findByRole("button", { name: "Escolher imagem" });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await userEvent.upload(input, new File(["png"], "logo.png", { type: "image/png" }));
    await waitFor(() => expect(forms).toEqual([["file"]]));
    expect(draw).not.toHaveBeenCalled();
  });

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
