import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { safeNext } from "../pages/SignInPage";
import { fakeApi, ME, notSignedIn, renderAt, TENANT } from "../test/render";

afterEach(() => {
  vi.unstubAllGlobals();
  window.location.hash = "";
});

describe("signing in", () => {
  it("sends people to sign in, then back where they were", async () => {
    let signedIn = false;
    fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/me": () => (signedIn ? { body: ME } : notSignedIn),
      "POST /api/session": () => {
        signedIn = true;
        return { body: ME };
      },
    });
    const router = renderAt("/algum/lugar");
    await screen.findByRole("heading", { name: "Entrar" });
    expect(router.state.location.search).toBe("?next=%2Falgum%2Flugar");

    await userEvent.type(screen.getByLabelText(/E-mail/), "ana@alinea.example");
    await userEvent.type(screen.getByLabelText(/Senha/), "a password");
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/algum/lugar"));
    expect(await screen.findByText("Página não encontrada")).toBeInTheDocument();
  });

  it("shows a wrong password in Portuguese, with the support code, never server text", async () => {
    fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/me": () => notSignedIn,
      "POST /api/session": () => ({
        status: 401,
        body: { error: "invalid_credentials" },
        headers: { "X-Request-ID": "req42" },
      }),
    });
    renderAt("/entrar");
    await userEvent.type(await screen.findByLabelText(/E-mail/), "ana@alinea.example");
    await userEvent.type(screen.getByLabelText(/Senha/), "wrong password");
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("E-mail ou senha incorretos.");
    expect(alert).toHaveTextContent("Código de suporte: req42");
  });

  it("uses the office's language before anyone signs in", async () => {
    fakeApi({ "GET /api/tenant": () => ({ body: { ...TENANT, locale: "en" } }), "GET /api/me": () => notSignedIn });
    renderAt("/entrar");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });

  it("only returns to addresses inside the painel", () => {
    expect(safeNext("/projetos")).toBe("/projetos");
    expect(safeNext("//evil.example/x")).toBe("/");
    expect(safeNext("https://evil.example")).toBe("/");
    expect(safeNext(null)).toBe("/");
  });
});

describe("signed in", () => {
  it("shows the projects page and signs out with the CSRF token", async () => {
    const sent = fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/me": () => ({ body: ME }),
      "DELETE /api/session": () => ({ status: 204 }),
    });
    const router = renderAt("/");
    expect(await screen.findByRole("heading", { name: "Projetos" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Sair" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/entrar"));
    const signOut = sent.find((request) => request.method === "DELETE");
    expect(signOut?.headers.get("X-CSRF-Token")).toBe("csrf-123");
  });

  it("on a phone, the ☰ drawer greets the person, goes to a section, switches the theme and signs out", async () => {
    localStorage.clear();
    fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/me": () => ({ body: { ...ME, name: "Ana Paula Souza" } }),
      "DELETE /api/session": () => ({ status: 204 }),
    });
    const router = renderAt("/");
    await screen.findByRole("heading", { name: "Projetos" });
    await userEvent.click(screen.getByRole("button", { name: "Menu" }));
    const menu = await screen.findByRole("dialog", { name: "Menu" });
    expect(within(menu).getByText("Olá, Ana")).toBeInTheDocument(); // the first name
    await userEvent.click(within(menu).getByRole("link", { name: "Configurações" }));
    await waitFor(() => expect(router.state.location.pathname).toMatch(/^\/configuracoes/));
    expect(screen.queryByRole("dialog", { name: "Menu" })).toBeNull(); // closed on the way
    await userEvent.click(screen.getByRole("button", { name: "Menu" }));
    const again = await screen.findByRole("dialog", { name: "Menu" });
    const dark = within(again).getByRole("switch", { name: "Modo escuro" });
    expect(dark).not.toBeChecked();
    await userEvent.click(dark);
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(localStorage.getItem("painel-theme")).toBe("dark"); // remembered on this device

    await userEvent.click(within(again).getByRole("button", { name: "Sair" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/entrar"));
  });


});

describe("the theme and the phone drawer", () => {
  it("keeps the top bar's button and the drawer's switch in step", async () => {
    localStorage.clear();
    document.documentElement.dataset.theme = "light";
    fakeApi({ "GET /api/tenant": () => ({ body: TENANT }), "GET /api/me": () => ({ body: ME }) });
    renderAt("/");
    await screen.findByRole("heading", { name: "Projetos" });
    await userEvent.click(screen.getByRole("button", { name: "Menu" }));
    const menu = await screen.findByRole("dialog", { name: "Menu" });
    await userEvent.click(within(menu).getByRole("switch", { name: "Modo escuro" }));
    // The top bar's button (desktop) follows: it now offers the light theme.
    expect(screen.getByRole("button", { name: "Usar tema claro", hidden: true })).toBeInTheDocument();
  });

  it("shows a failed sign-out inside the drawer, not behind it", async () => {
    fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/me": () => ({ body: ME }),
      "DELETE /api/session": () => ({ status: 500, body: {}, headers: { "X-Request-ID": "req7" } }),
    });
    renderAt("/");
    await screen.findByRole("heading", { name: "Projetos" });
    await userEvent.click(screen.getByRole("button", { name: "Menu" }));
    const menu = await screen.findByRole("dialog", { name: "Menu" });
    await userEvent.click(within(menu).getByRole("button", { name: "Sair" }));
    expect(await within(menu).findByRole("alert")).toHaveTextContent("req7");
  });
});

describe("choosing a password", () => {
  function linkApi(choose: (body: unknown) => { status?: number; body?: unknown }) {
    return fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/me": () => notSignedIn,
      "POST /api/password-link": () => ({ body: { email: "maria@alinea.example", name: "Maria", kind: "invite" } }),
      "POST /api/password": choose,
    });
  }

  it("greets the person, checks the repeat, signs them in, and drops the token from the address", async () => {
    const sent = linkApi(() => ({ body: { ...ME, name: "Maria" } }));
    window.location.hash = "#token=tok123";
    const router = renderAt("/definir-senha");
    expect(await screen.findByRole("heading", { name: "Escolha sua senha" })).toBeInTheDocument();
    expect(screen.getByText(/Olá, Maria/)).toBeInTheDocument();
    expect(window.location.hash).toBe("");

    await userEvent.type(screen.getByLabelText(/Nova senha/), "a long password");
    await userEvent.type(screen.getByLabelText(/Repita a senha/), "a different one");
    await userEvent.click(screen.getByRole("button", { name: "Salvar senha e entrar" }));
    expect(await screen.findByText("As senhas não são iguais.")).toBeInTheDocument();
    expect(sent.some((request) => request.path === "/api/password")).toBe(false);

    await userEvent.clear(screen.getByLabelText(/Repita a senha/));
    await userEvent.type(screen.getByLabelText(/Repita a senha/), "a long password");
    await userEvent.click(screen.getByRole("button", { name: "Salvar senha e entrar" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/"));
    expect(sent.find((request) => request.path === "/api/password")?.body).toEqual({
      token: "tok123",
      password: "a long password",
    });
  });

  it("explains a used or expired link instead of showing the form", async () => {
    fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/me": () => notSignedIn,
      "POST /api/password-link": () => ({ status: 404, body: { error: "link_invalid" } }),
    });
    window.location.hash = "#token=old";
    renderAt("/definir-senha");
    expect(await screen.findByRole("heading", { name: "Este link não funciona mais" })).toBeInTheDocument();
  });

  it("shows the server's verdict on a short password in the user's language", async () => {
    linkApi(() => ({ status: 422, body: { error: "password_too_short" } }));
    window.location.hash = "#token=tok123";
    renderAt("/definir-senha");
    // Past the browser's own length check, to see the server's answer handled.
    const field = await screen.findByLabelText(/Nova senha/);
    field.removeAttribute("minlength");
    await userEvent.type(field, "short");
    await userEvent.type(screen.getByLabelText(/Repita a senha/), "short");
    await userEvent.click(screen.getByRole("button", { name: "Salvar senha e entrar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("A senha precisa ter pelo menos 8 caracteres.");
  });
});
