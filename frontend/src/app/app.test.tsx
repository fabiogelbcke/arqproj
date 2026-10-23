import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { safeNext } from "../pages/SignInPage";
import { startPainelTour } from "./PainelTour";
import { fakeApi, ME, notSignedIn, renderAt, TENANT } from "../test/render";

// The painel tour runs Driver.js on the real screen; here only that "?" starts it.
vi.mock("./PainelTour", () => ({ startPainelTour: vi.fn() }));

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

  it("shows the password as typed on request, and says when Caps Lock is on", async () => {
    fakeApi({ "GET /api/tenant": () => ({ body: TENANT }), "GET /api/me": () => notSignedIn });
    renderAt("/entrar");
    const password = await screen.findByLabelText(/Senha/);
    await userEvent.type(password, "segredo");
    expect(password).toHaveAttribute("type", "password");
    await userEvent.click(screen.getByRole("button", { name: "Mostrar senha" }));
    expect(password).toHaveAttribute("type", "text");
    expect(password).toHaveValue("segredo");
    await userEvent.click(screen.getByRole("button", { name: "Ocultar senha" }));
    expect(password).toHaveAttribute("type", "password");

    expect(screen.queryByTitle("Caps Lock ativado")).toBeNull();
    const user = userEvent.setup(); // one keyboard, so Caps Lock stays on between calls
    await user.click(password);
    await user.keyboard("{CapsLock}A");
    expect(screen.getByTitle("Caps Lock ativado")).toBeInTheDocument();
    // Said to screen readers too, not only drawn.
    expect(screen.getAllByRole("status").some((status) => status.textContent === "Caps Lock ativado")).toBe(true);
    await user.keyboard("{CapsLock}a");
    expect(screen.queryByTitle("Caps Lock ativado")).toBeNull();
  });

  it("leaves Caps Lock to Apple's own mark on a Mac", async () => {
    vi.spyOn(navigator, "platform", "get").mockReturnValue("MacIntel");
    fakeApi({ "GET /api/tenant": () => ({ body: TENANT }), "GET /api/me": () => notSignedIn });
    renderAt("/entrar");
    const password = await screen.findByLabelText(/Senha/);
    const user = userEvent.setup();
    await user.click(password);
    await user.keyboard("{CapsLock}A");
    expect(screen.queryByTitle("Caps Lock ativado")).toBeNull();
    vi.restoreAllMocks();
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
    // Sair is in the account menu, under the round initial, with who is signed in.
    await userEvent.click(screen.getByRole("button", { name: "Sua conta" }));
    expect(screen.getByText(ME.email)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("menuitem", { name: "Sair" }));
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
    expect(localStorage.getItem("theme")).toBe("dark"); // remembered on this device

    await userEvent.click(within(again).getByRole("button", { name: "Sair" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/entrar"));
  });


});

describe("the painel tour", () => {
  it("starts from \"?\" in the top bar, and only from there", async () => {
    fakeApi({ "GET /api/tenant": () => ({ body: TENANT }), "GET /api/me": () => ({ body: ME }) });
    renderAt("/");
    await screen.findByRole("heading", { name: "Projetos" });
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(startPainelTour).not.toHaveBeenCalled(); // never on its own
    await userEvent.click(screen.getByRole("button", { name: "Ver o tour do painel" }));
    await waitFor(() => expect(startPainelTour).toHaveBeenCalledTimes(1));
  });

  it("starts from the account menu and the phone's drawer too", async () => {
    fakeApi({ "GET /api/tenant": () => ({ body: TENANT }), "GET /api/me": () => ({ body: ME }) });
    renderAt("/");
    await screen.findByRole("heading", { name: "Projetos" });
    await userEvent.click(screen.getByRole("button", { name: "Sua conta" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Ver o tour do painel" }));
    await waitFor(() => expect(startPainelTour).toHaveBeenCalledTimes(1));
    await userEvent.click(screen.getByRole("button", { name: "Menu" }));
    const drawer = await screen.findByRole("dialog", { name: "Menu" });
    await userEvent.click(within(drawer).getByRole("button", { name: "Ver o tour do painel" }));
    await waitFor(() => expect(startPainelTour).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Menu" })).toBeNull()); // out of the tour's way
  });
});

describe("the theme and the phone drawer", () => {
  it("keeps the account menu's switch and the drawer's in step", async () => {
    localStorage.clear();
    document.documentElement.dataset.theme = "light";
    fakeApi({ "GET /api/tenant": () => ({ body: TENANT }), "GET /api/me": () => ({ body: ME }) });
    renderAt("/");
    await screen.findByRole("heading", { name: "Projetos" });
    await userEvent.click(screen.getByRole("button", { name: "Menu" }));
    const menu = await screen.findByRole("dialog", { name: "Menu" });
    await userEvent.click(within(menu).getByRole("switch", { name: "Modo escuro" }));
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Menu" })).toBeNull());
    // The account menu (desktop) follows: its switch is on.
    await userEvent.click(screen.getByRole("button", { name: "Sua conta" }));
    const dark = screen.getByRole("menuitemcheckbox", { name: "Modo escuro" });
    expect(dark).toBeChecked();
    // Switching it off there: the light theme, and the menu stays open for more.
    await userEvent.click(dark);
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(localStorage.getItem("theme")).toBe("light");
    expect(screen.getByRole("menuitemcheckbox", { name: "Modo escuro" })).not.toBeChecked();
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
    expect(screen.getByRole("link", { name: "Pedir um novo link" })).toHaveAttribute("href", "/esqueci-a-senha");
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

describe("whose panel this is", () => {
  it("shows Unio with the office's logo", async () => {
    fakeApi({
      "GET /api/tenant": () => ({ body: { ...TENANT, logo_url: "/api/office/logo?v=1", logo_dark_url: null } }),
      "GET /api/me": () => notSignedIn,
    });
    renderAt("/entrar");
    expect(await screen.findByRole("img", { name: "Alinea" })).toHaveAttribute("src", "/api/office/logo?v=1");
    expect(screen.getAllByRole("img", { name: "Unio" }).length).toBeGreaterThan(0);
  });

  it("or with its name, without a logo", async () => {
    fakeApi({ "GET /api/tenant": () => ({ body: TENANT }), "GET /api/me": () => notSignedIn });
    renderAt("/entrar");
    expect(await screen.findByText("Alinea", { selector: "span" })).toBeInTheDocument();
  });
});

describe("a forgotten password", () => {
  it("asks for a link by email, and says the same whatever the address", async () => {
    const sent = fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/me": () => notSignedIn,
      "POST /api/password-reset": () => ({ status: 204 }),
    });
    renderAt("/entrar");
    await userEvent.click(await screen.findByRole("link", { name: "Esqueceu a senha?" }));
    await userEvent.type(await screen.findByLabelText(/E-mail/), "ana@alinea.example");
    await userEvent.click(screen.getByRole("button", { name: "Enviar link" }));
    expect(await screen.findByRole("heading", { name: "Confira seu e-mail" })).toBeInTheDocument();
    expect(screen.getByText(/Se ana@alinea.example tiver uma conta no painel de Alinea/)).toBeInTheDocument();
    expect(sent.find((r) => r.path === "/api/password-reset")?.body).toEqual({ email: "ana@alinea.example" });
  });

  it("says when to wait, after too many requests", async () => {
    fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/me": () => notSignedIn,
      "POST /api/password-reset": () => ({ status: 429, body: { error: "too_many_attempts" } }),
    });
    renderAt("/esqueci-a-senha");
    await userEvent.type(await screen.findByLabelText(/E-mail/), "ana@alinea.example");
    await userEvent.click(screen.getByRole("button", { name: "Enviar link" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});

describe("the office's mark in the top bar", () => {
  it("leads back to the projects from anywhere, settings included", async () => {
    fakeApi({ "GET /api/tenant": () => ({ body: TENANT }), "GET /api/me": () => ({ body: ME }) });
    const router = renderAt("/configuracoes/escritorio");
    const brand = await screen.findByRole("link", { name: "Alinea" }); // no logo: the office's name
    await userEvent.click(brand);
    await waitFor(() => expect(router.state.location.pathname).toBe("/"));
  });
});

describe("each screen's title and the skip link", () => {
  it("names the screen and the office in the browser tab", async () => {
    fakeApi({ "GET /api/tenant": () => ({ body: TENANT }), "GET /api/me": () => ({ body: ME }) });
    const router = renderAt("/");
    await screen.findByRole("heading", { name: "Projetos" });
    await waitFor(() => expect(document.title).toBe("Projetos · Alinea"));
    await router.navigate("/configuracoes/equipe");
    await waitFor(() => expect(document.title).toBe("Equipe · Configurações · Alinea"));
  });

  it("names the sign-in screen before anyone is signed in", async () => {
    fakeApi({ "GET /api/tenant": () => ({ body: TENANT }), "GET /api/me": () => ({ status: 401, body: { error: "not_signed_in" } }) });
    renderAt("/entrar");
    await screen.findByRole("heading", { name: "Entrar" });
    await waitFor(() => expect(document.title).toBe("Entrar · Alinea"));
  });

  it("names the password screen the same for an invite, a reset and a spent link", async () => {
    fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/me": () => ({ status: 401, body: { error: "not_signed_in" } }),
      "POST /api/password-link": () => ({ body: { email: "ana@alinea.example", name: "Ana", kind: "reset" } }),
    });
    window.location.hash = "#token=abc";
    renderAt("/definir-senha");
    await screen.findByRole("heading", { name: "Escolha uma nova senha" });
    await waitFor(() => expect(document.title).toBe("Definir senha · Alinea"));
  });

  it("names a spent password link's screen the same", async () => {
    fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/me": () => ({ status: 401, body: { error: "not_signed_in" } }),
      "POST /api/password-link": () => ({ status: 404, body: { error: "link_invalid" } }),
    });
    window.location.hash = "#token=old";
    renderAt("/definir-senha");
    await screen.findByRole("heading", { name: /link/i });
    await waitFor(() => expect(document.title).toBe("Definir senha · Alinea"));
  });

  it("skips the top bar to the page's content, first thing on Tab", async () => {
    fakeApi({ "GET /api/tenant": () => ({ body: TENANT }), "GET /api/me": () => ({ body: ME }) });
    renderAt("/");
    await screen.findByRole("heading", { name: "Projetos" });
    await userEvent.tab();
    const skip = screen.getByRole("link", { name: "Pular para o conteúdo" });
    expect(skip).toHaveFocus();
    expect(skip).toHaveAttribute("href", "#content");
    expect(document.getElementById("content")?.tagName).toBe("MAIN");
  });
});
