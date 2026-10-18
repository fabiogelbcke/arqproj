import { screen, waitFor, within } from "@testing-library/react";
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

describe("the painel's Drive banner", () => {
  it("warns when the portal cannot read the folder", async () => {
    api({ ...CONNECTED, reader_status: "no_access" });
    renderAt("/");
    expect(await screen.findByText(/O portal não consegue ler a pasta/)).toBeInTheDocument();
  });

  it("shows a status failure with its support code instead of nothing", async () => {
    fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/me": () => ({ body: ME }),
      "GET /api/drive": () => ({ status: 500, body: {}, headers: { "X-Request-ID": "req9" } }),
      "GET /api/onboarding": () => ({ body: { storage_connected: true, has_project: true } }),
    });
    renderAt("/");
    expect(await screen.findByRole("alert", {}, { timeout: 4000 })).toHaveTextContent("req9");
  });
});

describe("another Google account", () => {
  const BEFORE = { ...CONNECTED, writer_status: "none", has_folder: true, account_email: "escritorio@gmail.com" };

  it("offers the same account again, or another behind a clear warning", async () => {
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign, origin: window.location.origin });
    const sent = api(BEFORE, {
      "POST /api/drive/connect": () => ({ body: { url: "https://accounts.google.com/o/oauth2/v2/auth?x" } }),
    });
    renderAt("/configuracoes/drive");
    expect(await screen.findByText(/Antes conectado como escritorio@gmail.com/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reconectar a mesma conta" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Usar outra conta" }));
    const warning = await screen.findByRole("alertdialog", { name: "Usar outra conta Google?" });
    expect(warning).toHaveTextContent("Os arquivos dos projetos não vêm para a nova conta");
    await userEvent.click(within(warning).getByRole("button", { name: "Entendi, usar outra conta" }));
    await waitFor(() => expect(assign).toHaveBeenCalled());
    expect(sent.find((r) => r.path === "/api/drive/connect")?.body).toEqual({ fresh: true });
  });

  it("a failure to start the switch shows in the warning itself, with its support code", async () => {
    api(BEFORE, {
      "POST /api/drive/connect": () => ({ status: 503, body: { error: "drive_connect_failed" }, headers: { "X-Request-ID": "req5" } }),
    });
    renderAt("/configuracoes/drive");
    await userEvent.click(await screen.findByRole("button", { name: "Usar outra conta" }));
    const warning = await screen.findByRole("alertdialog", { name: "Usar outra conta Google?" });
    await userEvent.click(within(warning).getByRole("button", { name: "Entendi, usar outra conta" }));
    expect(await within(warning).findByRole("alert")).toHaveTextContent("req5");
  });

  it("reconnecting the same account doesn't start afresh", async () => {
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign, origin: window.location.origin });
    const sent = api(BEFORE, {
      "POST /api/drive/connect": () => ({ body: { url: "https://accounts.google.com/o/oauth2/v2/auth?x" } }),
    });
    renderAt("/configuracoes/drive");
    await userEvent.click(await screen.findByRole("button", { name: "Reconectar a mesma conta" }));
    await waitFor(() => expect(sent.find((r) => r.path === "/api/drive/connect")?.body).toEqual({ fresh: false }));
  });

  it("after Google returns another account, offers to use it anyway", async () => {
    window.history.pushState({}, "", "/painel/configuracoes/drive?erro=drive_other_account");
    api(BEFORE);
    renderAt("/configuracoes/drive?erro=drive_other_account");
    expect(await screen.findByRole("button", { name: "Usar esta outra conta mesmo assim" })).toBeInTheDocument();
  });

  it("while connected, offers to disconnect first rather than to switch", async () => {
    api({ ...CONNECTED, has_folder: true });
    renderAt("/configuracoes/drive");
    expect(await screen.findByRole("button", { name: "Desconectar" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Usar outra conta/ })).toBeNull();
  });

  it("a first connection has no switch to offer", async () => {
    api(NOT_CONNECTED);
    renderAt("/configuracoes/drive");
    await screen.findByText("Não conectado");
    expect(screen.queryByRole("button", { name: /Usar outra conta/ })).toBeNull();
  });
});

describe("the Drive's space", () => {
  it("shows how much is used, and warns from 80%", async () => {
    api(CONNECTED, { "GET /api/drive/space": () => ({ body: { used: 12 * 2 ** 30, total: 15 * 2 ** 30 } }) });
    renderAt("/configuracoes/drive");
    expect(await screen.findByText("12 GB de 15 GB usados (80%)")).toBeInTheDocument();
    expect(screen.getByRole("meter", { name: "Espaço no Google Drive" })).toHaveAttribute("aria-valuenow", "80");
    expect(screen.getByText(/Pouco espaço livre/)).toBeInTheDocument();
  });

  it("doesn't warn with room to spare, and shows small amounts in MB", async () => {
    api(CONNECTED, { "GET /api/drive/space": () => ({ body: { used: 850 * 2 ** 20, total: 15 * 2 ** 30 } }) });
    renderAt("/configuracoes/drive");
    expect(await screen.findByText("850 MB de 15 GB usados (6%)")).toBeInTheDocument();
    expect(screen.queryByText(/Pouco espaço livre/)).toBeNull();
  });

  it("says pooled Workspace storage has no total of its own", async () => {
    api(CONNECTED, { "GET /api/drive/space": () => ({ body: { used: 3.5 * 2 ** 30, total: null } }) });
    renderAt("/configuracoes/drive");
    expect(await screen.findByText("Armazenamento compartilhado (Workspace): 3,5 GB usados")).toBeInTheDocument();
  });

  it("says when it couldn't be checked, with the support code, without Google's words", async () => {
    api(CONNECTED, {
      "GET /api/drive/space": () => ({ status: 503, body: { error: "drive_connect_failed" }, headers: { "X-Request-ID": "req7" } }),
    });
    renderAt("/configuracoes/drive");
    expect(await screen.findByText(/Não foi possível ver o espaço do Drive agora\. .*req7/)).toBeInTheDocument();
  });

  it("offers to reconnect when access was withdrawn since the page loaded", async () => {
    let status: object = CONNECTED;
    api({}, {
      "GET /api/drive": () => ({ body: status }),
      "GET /api/drive/space": () => {
        status = { ...CONNECTED, writer_status: "expired" }; // marked by the server just now
        return { status: 409, body: { error: "drive_expired" } };
      },
    });
    renderAt("/configuracoes/drive");
    expect(await screen.findByRole("button", { name: "Reconectar" })).toBeInTheDocument();
  });
});

describe("the painel's first steps", () => {
  it("shows a new office's owner what's left, with a button for each step", async () => {
    api(NOT_CONNECTED);
    renderAt("/");
    const steps = await screen.findByRole("region", { name: "Primeiros passos" });
    expect(within(steps).getByLabelText("0 de 3 passos concluídos")).toBeInTheDocument();
    expect(within(steps).getByRole("link", { name: "Conectar" })).toHaveAttribute("href", "/configuracoes/drive");
    expect(within(steps).getByRole("button", { name: "Personalizar" })).toBeInTheDocument(); // a dialog, on this page
    expect(within(steps).getByRole("button", { name: "Criar projeto" })).toBeInTheDocument();
    // The boxes tick themselves: nothing to click.
    expect(within(steps).queryByRole("checkbox")).toBeNull();
    // Not connected yet is this list's first step, not a separate notice.
    expect(screen.queryByText(/Conecte o Google Drive para criar projetos/)).toBeNull();
  });

  it("ticks a finished step, with no button for it", async () => {
    api(NOT_CONNECTED, {
      "GET /api/onboarding": () => ({ body: { storage_connected: true, office_details: false, has_project: false } }),
    });
    renderAt("/");
    const steps = await screen.findByRole("region", { name: "Primeiros passos" });
    expect(within(steps).getByLabelText("1 de 3 passos concluídos")).toBeInTheDocument();
    const drive = within(steps).getByText("Conectar o Google Drive").closest("li")!;
    expect(drive).toHaveAttribute("data-done");
    expect(within(drive).getByText("Concluído")).toBeInTheDocument();
    expect(within(drive).queryByRole("link")).toBeNull();
  });

  it("offers the example project beside the steps, not as one, and still once they are done", async () => {
    api(NOT_CONNECTED);
    renderAt("/");
    const steps = await screen.findByRole("region", { name: "Primeiros passos" });
    expect(within(steps).getByRole("link", { name: "Ver um projeto de exemplo" })).toHaveAttribute("href", "/tour-projeto");
    expect(within(steps).getByLabelText("0 de 3 passos concluídos")).toBeInTheDocument(); // not counted
  });

  it("keeps the example project at hand once the steps are done", async () => {
    api(NOT_CONNECTED, {
      "GET /api/onboarding": () => ({ body: { storage_connected: true, office_details: true, has_project: true } }),
    });
    renderAt("/");
    expect(await screen.findByRole("link", { name: "Ver um projeto de exemplo" })).toHaveAttribute("href", "/tour-projeto");
    expect(screen.queryByRole("region", { name: "Primeiros passos" })).toBeNull();
  });

  it("the first project's button opens the new-project dialog", async () => {
    api(NOT_CONNECTED);
    renderAt("/");
    const steps = await screen.findByRole("region", { name: "Primeiros passos" });
    await userEvent.click(within(steps).getByRole("button", { name: "Criar projeto" }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });

  it("shows members the steps without buttons, and who can do them", async () => {
    api(NOT_CONNECTED, {}, { ...ME, role: "member" });
    renderAt("/");
    const steps = await screen.findByRole("region", { name: "Primeiros passos" });
    // Only the example project, which isn't a step.
    expect(within(steps).getAllByRole("link").map((link) => link.textContent)).toEqual(["Ver um projeto de exemplo"]);
    expect(within(steps).queryByRole("button")).toBeNull();
    expect(within(steps).getByText(/Só o responsável pelo escritório/)).toBeInTheDocument();
  });
});

