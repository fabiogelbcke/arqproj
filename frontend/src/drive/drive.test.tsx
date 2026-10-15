import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, ME, renderAt, TENANT } from "../test/render";

const NOT_CONNECTED = {
  kind: null,
  writer_status: "none",
  reader_status: "unknown",
  account_email: null,
  folder_url: null,
  can_manage: true,
};
const CONNECTED = {
  ...NOT_CONNECTED,
  kind: "google",
  writer_status: "connected",
  reader_status: "ok",
  account_email: "escritorio@gmail.com",
  folder_url: "https://drive.google.com/drive/folders/root1",
};

function api(drive: object, extra: Record<string, (body: unknown) => object> = {}, me = ME) {
  return fakeApi({
    "GET /api/tenant": () => ({ body: TENANT }),
    "GET /api/me": () => ({ body: me }),
    "GET /api/drive": () => ({ body: drive }),
    "GET /api/onboarding": () => ({ body: { storage_connected: false, has_project: false } }),
    ...extra,
  });
}

afterEach(() => vi.unstubAllGlobals());

describe("Drive settings", () => {
  it("connects by going to Google's sign-in", async () => {
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign, origin: window.location.origin });
    const sent = api(NOT_CONNECTED, {
      "POST /api/drive/connect": () => ({ body: { url: "https://accounts.google.com/o/oauth2/v2/auth?x" } }),
    });
    renderAt("/configuracoes/drive");
    expect(await screen.findByText("Não conectado")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Conectar Google Drive" }));
    await waitFor(() => expect(assign).toHaveBeenCalledWith("https://accounts.google.com/o/oauth2/v2/auth?x"));
    expect(sent.find((r) => r.path === "/api/drive/connect")?.headers.get("X-CSRF-Token")).toBe("csrf-123");
  });

  it("shows the account and asks before disconnecting", async () => {
    const sent = api(CONNECTED, { "DELETE /api/drive": () => ({ status: 204 }) });
    renderAt("/configuracoes/drive");
    expect(await screen.findByText("Conectado como escritorio@gmail.com")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Desconectar" }));
    expect(screen.getByText(/deixa de acessar o Drive/)).toBeInTheDocument();
    expect(sent.some((r) => r.method === "DELETE")).toBe(false); // not yet: confirm first
    await userEvent.click(screen.getByRole("button", { name: "Desconectar" }));
    await waitFor(() => expect(sent.some((r) => r.method === "DELETE")).toBe(true));
  });

  it("offers a reconnect when the connection expired", async () => {
    api({ ...CONNECTED, writer_status: "expired" });
    renderAt("/configuracoes/drive");
    expect(await screen.findByText("Conexão expirada")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reconectar" })).toBeInTheDocument();
  });

  it("explains a failed connection from Google's return, in Portuguese", async () => {
    api(NOT_CONNECTED);
    renderAt("/configuracoes/drive?erro=drive_share_failed&ref=req42");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Não foi possível preparar a pasta");
    expect(alert).toHaveTextContent("Código de suporte: req42");
  });

  it("lets members see the connection but not change it", async () => {
    api({ ...CONNECTED, can_manage: false }, {}, { ...ME, role: "member" });
    renderAt("/configuracoes/drive");
    expect(await screen.findByText(/Só o responsável/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Desconectar" })).toBeNull();
  });
});

describe("Drive status unavailable", () => {
  it("says so with the support code instead of loading forever", async () => {
    fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/me": () => ({ body: ME }),
      "GET /api/drive": () => ({ status: 500, body: {}, headers: { "X-Request-ID": "req7" } }),
      "GET /api/onboarding": () => ({ body: { storage_connected: false, has_project: false } }),
    });
    renderAt("/configuracoes/drive");
    const alert = await screen.findByRole("alert", {}, { timeout: 4000 });
    expect(alert).toHaveTextContent("Algo deu errado");
    expect(alert).toHaveTextContent("req7");
  });
});

describe("the painel's first steps", () => {
  it("points a new office's owner to connecting Drive", async () => {
    api(NOT_CONNECTED);
    renderAt("/");
    expect(await screen.findByRole("heading", { name: "Primeiros passos" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Conectar onde ficam os arquivos/ })).toHaveAttribute(
      "href",
      "/configuracoes/drive",
    );
    expect(screen.getByText(/Conecte o Google Drive para criar projetos/)).toBeInTheDocument();
  });
});
