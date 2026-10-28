import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, ME, renderAt, TENANT } from "../test/render";

afterEach(() => vi.unstubAllGlobals());

function signedIn(extra: Parameters<typeof fakeApi>[0] = {}) {
  let me: typeof ME & { email_confirmed?: boolean } = ME;
  const sent = fakeApi({
    // The server's own account, as the email change leaves it.
    "POST /api/me/email/change": (body) => {
      me = { ...me, email: (body as { email: string }).email, email_confirmed: false };
      return { body: me };
    },
    "GET /api/tenant": () => ({ body: TENANT }),
    "GET /api/me": () => ({ body: me }),
    "PATCH /api/me": (body) => {
      me = { ...me, name: (body as { name: string }).name };
      return { status: 204 };
    },
    "GET /api/projects": () => ({ body: [] }),
    ...extra,
  });
  return sent;
}

describe("Minha conta", () => {
  it("is in the account menu, with the person's name and email", async () => {
    signedIn();
    const router = renderAt("/");
    await userEvent.click(await screen.findByRole("button", { name: "Sua conta" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Minha conta" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/conta"));
    expect(screen.getByRole("heading", { level: 1, name: "Minha conta" })).toBeInTheDocument();
    expect(screen.getByLabelText(/Seu nome/)).toHaveValue(ME.name);
    expect(screen.getByLabelText(/E-mail/)).toHaveValue(ME.email);
    expect(screen.getByLabelText(/E-mail/)).toHaveAttribute("readonly");
  });

  it("is in the phone drawer too", async () => {
    signedIn();
    const router = renderAt("/");
    await userEvent.click(await screen.findByRole("button", { name: "Menu" }));
    await userEvent.click(within(screen.getByRole("dialog", { name: "Menu" })).getByRole("link", { name: "Minha conta" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/conta"));
  });

  it("renames the person, saving only once the name changed", async () => {
    const sent = signedIn();
    renderAt("/conta");
    const save = (await screen.findAllByRole("button", { name: "Salvar" }))[0]!;
    expect(save).toBeDisabled();
    const name = screen.getByLabelText(/Seu nome/);
    await userEvent.clear(name);
    await userEvent.type(name, "Ana Paula");
    await userEvent.click(save);
    expect(await screen.findByText("Nome salvo.")).toBeInTheDocument();
    expect(sent.find((r) => r.method === "PATCH")?.body).toEqual({ name: "Ana Paula" });
    await waitFor(() => expect(screen.getByLabelText(/Seu nome/)).toHaveValue("Ana Paula"));
  });

  it("changes the password with the current one, then carries on with the new session's token", async () => {
    const sent = signedIn({
      "POST /api/me/password": () => ({ body: { ...ME, csrf_token: "csrf-new" } }),
    });
    renderAt("/conta");
    await userEvent.type(await screen.findByLabelText(/Senha atual/), "a good password");
    await userEvent.type(screen.getByLabelText(/^Nova senha/), "uma senha nova e boa");
    await userEvent.type(screen.getByLabelText(/Repita a senha/), "uma senha nova e boa");
    await userEvent.click(screen.getByRole("button", { name: "Alterar senha" }));
    expect(await screen.findByText("Senha alterada. Os outros aparelhos foram desconectados.")).toBeInTheDocument();
    expect(sent.find((r) => r.path === "/api/me/password")?.body).toEqual({
      current: "a good password",
      password: "uma senha nova e boa",
    });
    expect(screen.getByLabelText(/Senha atual/)).toHaveValue(""); // a fresh form
    // The next change goes with the new session's token.
    const name = screen.getByLabelText(/Seu nome/);
    await userEvent.type(name, "!");
    await userEvent.click(screen.getAllByRole("button", { name: "Salvar" })[0]!);
    await waitFor(() => expect(sent.find((r) => r.method === "PATCH")?.headers.get("X-CSRF-Token")).toBe("csrf-new"));
  });

  it("changes the email with the current password, then asks for the code sent to it", async () => {
    const sent = signedIn();
    renderAt("/conta");
    await userEvent.click(await screen.findByRole("button", { name: "Alterar e-mail" }));
    const dialog = screen.getByRole("dialog", { name: "Alterar e-mail" });
    expect(dialog).toHaveTextContent("O e-mail atual será avisado da troca.");
    await userEvent.type(within(dialog).getByLabelText(/Novo e-mail/), "ana.nova@alinea.example");
    await userEvent.type(within(dialog).getByLabelText(/Senha atual/), "a good password");
    await userEvent.click(within(dialog).getByRole("button", { name: "Enviar código" }));
    await waitFor(() =>
      expect(sent.find((r) => r.path === "/api/me/email/change")?.body).toEqual({
        email: "ana.nova@alinea.example",
        current: "a good password",
      }),
    );
    // Unconfirmed now: the painel shows the code screen, naming the new address.
    expect(await screen.findByRole("heading", { name: "Confirme seu e-mail" })).toBeInTheDocument();
    expect(document.body).toHaveTextContent("ana.nova@alinea.example");
    expect(screen.queryByRole("heading", { level: 1, name: "Minha conta" })).toBeNull();
  });

  it("says when the current password is wrong", async () => {
    signedIn({
      "POST /api/me/password": () => ({ status: 422, body: { error: "current_password_wrong" } }),
    });
    renderAt("/conta");
    await userEvent.type(await screen.findByLabelText(/Senha atual/), "not it");
    await userEvent.type(screen.getByLabelText(/^Nova senha/), "uma senha nova e boa");
    await userEvent.type(screen.getByLabelText(/Repita a senha/), "uma senha nova e boa");
    await userEvent.click(screen.getByRole("button", { name: "Alterar senha" }));
    expect(await screen.findByText(/A senha atual não confere/)).toBeInTheDocument();
  });
});
