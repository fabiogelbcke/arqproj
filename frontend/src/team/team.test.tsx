import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, ME, renderAt, TENANT } from "../test/render";

const DONA = { id: "u-1", name: "Ana Lima", email: "dona@alinea.example", role: "owner", status: "active", me: true };
const BIA = { id: "u-2", name: "Bia Souza", email: "bia@alinea.example", role: "member", status: "invited", me: false };

function api(team: { members?: object[]; join_link?: object; can_manage?: boolean } = {}, extra = {}) {
  let members = team.members ?? [DONA];
  return fakeApi({
    "GET /api/tenant": () => ({ body: TENANT }),
    "GET /api/me": () => ({ body: ME }),
    "GET /api/drive": () => ({ body: { kind: "folder", writer_status: "none", reader_status: "unknown", can_manage: true } }),
    "GET /api/onboarding": () => ({ body: { storage_connected: true, office_details: true, has_project: true } }),
    "GET /api/team": () => ({
      body: { members, join_link: team.join_link ?? { on: false, expires_at: null }, can_manage: team.can_manage ?? true },
    }),
    "POST /api/team/invites": (body: unknown) => {
      const { name, email, role } = body as { name: string; email: string; role: string };
      const member = { id: "u-9", name, email, role, status: "invited", me: false };
      members = [...members, member];
      return { status: 201, body: { member, link: "http://alinea.localhost/painel/definir-senha#token=abc", emailed: true } };
    },
    ...extra,
  });
}

const writeText = vi.fn(async () => undefined);
afterEach(() => {
  vi.unstubAllGlobals();
  writeText.mockClear();
});

describe("Configurações → Equipe", () => {
  it("lists who's in and who's invited", async () => {
    api({ members: [DONA, BIA] });
    renderAt("/configuracoes/equipe");
    const list = await screen.findByRole("list", { name: "Equipe" });
    const [ana, bia] = within(list).getAllByRole("listitem");
    expect(ana).toHaveTextContent("Ana Lima (você)dona@alinea.example");
    expect(ana).toHaveTextContent("Administrador(a)");
    expect(bia).toHaveTextContent("Convite pendente");
  });

  it("invites a person by email, and offers the link to copy as well", async () => {
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
    const sent = api();
    renderAt("/configuracoes/equipe");
    await userEvent.click(await screen.findByRole("button", { name: "Convidar pessoa" }));
    await userEvent.type(await screen.findByLabelText("Nome"), "Caio Reis");
    await userEvent.type(screen.getByLabelText("E-mail"), "Caio@Gmail.com");
    await userEvent.click(screen.getByRole("radio", { name: /Administrador/ }));
    await userEvent.click(screen.getByRole("button", { name: "Enviar convite" }));
    expect(await screen.findByText(/Convite enviado para caio@gmail.com/)).toBeInTheDocument();
    expect(sent.find((r) => r.method === "POST")?.body).toEqual({ name: "Caio Reis", email: "caio@gmail.com", role: "owner" });
    await userEvent.click(screen.getByRole("button", { name: "Copiar link" }));
    expect(writeText).toHaveBeenCalledWith("http://alinea.localhost/painel/definir-senha#token=abc");
    // Done, or the next person.
    await userEvent.click(screen.getByRole("button", { name: "Convidar outra pessoa" }));
    expect(screen.getByLabelText("Nome")).toHaveValue("");
    await userEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("says so when the email couldn't go, and the link is there to send", async () => {
    api({}, {
      "POST /api/team/invites": () => ({
        status: 201,
        body: { member: { ...BIA, id: "u-9" }, link: "http://x/painel/definir-senha#token=abc", emailed: false },
      }),
    });
    renderAt("/configuracoes/equipe");
    await userEvent.click(await screen.findByRole("button", { name: "Convidar pessoa" }));
    await userEvent.type(await screen.findByLabelText("Nome"), "Bia");
    await userEvent.type(screen.getByLabelText("E-mail"), "bia@alinea.example");
    await userEvent.click(screen.getByRole("button", { name: "Enviar convite" }));
    expect(await screen.findByText(/Não foi possível enviar o e-mail/)).toBeInTheDocument();
    expect(screen.getByLabelText("Link do convite")).toHaveValue("http://x/painel/definir-senha#token=abc");
  });

  it("names who already has the address", async () => {
    api({}, {
      "POST /api/team/invites": () => ({ status: 409, body: { error: "already_staff", conflict_name: "Ana Lima" } }),
    });
    renderAt("/configuracoes/equipe");
    await userEvent.click(await screen.findByRole("button", { name: "Convidar pessoa" }));
    await userEvent.type(await screen.findByLabelText("Nome"), "Ana");
    await userEvent.type(screen.getByLabelText("E-mail"), "dona@alinea.example");
    await userEvent.click(screen.getByRole("button", { name: "Enviar convite" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Ana Lima já faz parte da equipe com este e-mail.");
  });

  it("sends a pending invite again, with its new link, or cancels it", async () => {
    const sent = api({ members: [DONA, BIA] }, {
      "POST /api/team/invites/u-2/link": () => ({ body: { member: BIA, link: "http://x/#token=new", emailed: true } }),
      "DELETE /api/team/invites/u-2": () => ({ status: 204 }),
    });
    renderAt("/configuracoes/equipe");
    await userEvent.click(await screen.findByRole("button", { name: "Reenviar" }));
    expect(await screen.findByText("Convite reenviado para bia@alinea.example.")).toBeInTheDocument();
    expect(screen.getByLabelText("Link do convite de Bia Souza")).toHaveValue("http://x/#token=new");
    await userEvent.click(screen.getByRole("button", { name: "Cancelar convite" }));
    await waitFor(() => expect(sent.some((r) => r.method === "DELETE")).toBe(true));
  });

  it("turns the shared link on, shows it once to copy, and off", async () => {
    let on = false;
    api(
      {},
      {
        "GET /api/team": () => ({
          body: { members: [DONA], join_link: { on, expires_at: on ? "2026-10-21T12:00:00Z" : null }, can_manage: true },
        }),
        "POST /api/team/join-link": () => {
          on = true;
          return { status: 201, body: { link: "http://alinea.localhost/painel/entrar-na-equipe#token=xyz", expires_at: "2026-10-21T12:00:00Z" } };
        },
        "DELETE /api/team/join-link": () => {
          on = false;
          return { status: 204 };
        },
      },
    );
    renderAt("/configuracoes/equipe");
    await userEvent.click(await screen.findByRole("button", { name: "Criar link da equipe" }));
    expect(await screen.findByLabelText("Convidar através de um link")).toHaveValue("http://alinea.localhost/painel/entrar-na-equipe#token=xyz");
    expect(screen.getByText(/o link só aparece uma vez e vale por 24 horas/)).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Criar novo link" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Desativar link" }));
    expect(await screen.findByRole("button", { name: "Criar link da equipe" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Convidar através de um link")).toBeNull();
  });

  it("says until when a shared link made earlier works", async () => {
    api({ join_link: { on: true, expires_at: "2026-10-21T15:30:00Z" } });
    renderAt("/configuracoes/equipe");
    expect(await screen.findByText("Há um link ativo até 21/10, 12:30.")).toBeInTheDocument(); // São Paulo
    expect(screen.queryByLabelText("Convidar através de um link")).toBeNull(); // shown only when made
  });

  it("a member sees the team, without invites or the shared link", async () => {
    api({ members: [DONA, BIA], can_manage: false });
    renderAt("/configuracoes/equipe");
    expect(await screen.findByText("Só administradores convidam pessoas.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Convidar pessoa" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Reenviar" })).toBeNull();
    expect(screen.queryByText("Convidar através de um link")).toBeNull();
  });
});

describe("the signup link's page", () => {
  it.each([
    { role: "member", title: "Entrar na equipe do Alinea" },
    { role: "owner", title: "Criar a conta de proprietário do Alinea" },
  ])("the $role link asks for a name, an email and a password, then for the emailed code", async ({ role, title }) => {
    window.history.replaceState(null, "", "/entrar-na-equipe#token=xyz");
    const caio = { ...ME, name: "Caio Reis", email: "caio@gmail.com", role, email_confirmed: false };
    const sent = api(
      {},
      {
        "GET /api/me": () => ({ status: 401, body: { error: "not_signed_in" } }),
        "POST /api/join/check": () => ({ body: { office: "Alinea", role } }),
        "POST /api/join": () => ({ status: 201, body: caio }),
        "POST /api/me/email-code": (body: unknown) =>
          (body as { code: string }).code === "123456"
            ? { body: { ...caio, email_confirmed: true } }
            : { status: 422, body: { error: "email_code_wrong" } },
        "GET /api/projects": () => ({ body: [] }),
      },
    );
    renderAt("/entrar-na-equipe#token=xyz");
    expect(await screen.findByRole("heading", { name: title })).toBeInTheDocument();
    expect(window.location.hash).toBe(""); // the token leaves the address bar
    await userEvent.type(screen.getByLabelText("Nome"), "Caio Reis");
    await userEvent.type(screen.getByLabelText("E-mail"), "caio@gmail.com");
    await userEvent.type(screen.getByLabelText(/^Nova senha/), "uma boa senha");
    await userEvent.type(screen.getByLabelText(/^Repita a senha/), "uma boa senha");
    await userEvent.click(screen.getByRole("button", { name: "Criar conta" }));
    expect(await screen.findByRole("heading", { name: "Confirme seu e-mail" })).toBeInTheDocument();
    expect(screen.getByText(/código de 6 dígitos para caio@gmail.com/)).toBeInTheDocument();
    expect(sent.find((r) => r.path === "/api/join")?.body).toEqual({
      token: "xyz",
      name: "Caio Reis",
      email: "caio@gmail.com",
      password: "uma boa senha",
    });
    // Only letters typed are dropped; a wrong code says so.
    await userEvent.type(screen.getByLabelText(/^Código/), "12a3450");
    expect(screen.getByLabelText(/^Código/)).toHaveValue("123450");
    await userEvent.click(screen.getByRole("button", { name: "Confirmar" }));
    expect(await screen.findByText("Código incorreto. Confira o e-mail e tente de novo.")).toBeInTheDocument();
    await userEvent.clear(screen.getByLabelText(/^Código/));
    await userEvent.type(screen.getByLabelText(/^Código/), "123456");
    await userEvent.click(screen.getByRole("button", { name: "Confirmar" }));
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Confirme seu e-mail" })).not.toBeInTheDocument());
    expect(screen.getByRole("link", { name: "Projetos" })).toBeInTheDocument(); // the painel
  });

  it("refuses an address that already has an account", async () => {
    window.history.replaceState(null, "", "/entrar-na-equipe#token=xyz");
    fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/me": () => ({ status: 401, body: { error: "not_signed_in" } }),
      "POST /api/join/check": () => ({ body: { office: "Alinea", role: "member" } }),
      "POST /api/join": () => ({ status: 409, body: { error: "account_exists" } }),
    });
    renderAt("/entrar-na-equipe#token=xyz");
    await userEvent.type(await screen.findByLabelText("Nome"), "Ana");
    await userEvent.type(screen.getByLabelText("E-mail"), "dona@alinea.example");
    await userEvent.type(screen.getByLabelText(/^Nova senha/), "uma boa senha");
    await userEvent.type(screen.getByLabelText(/^Repita a senha/), "uma boa senha");
    await userEvent.click(screen.getByRole("button", { name: "Criar conta" }));
    expect(await screen.findByText(/Já existe uma conta com este e-mail/)).toBeInTheDocument();
  });

  it("says when the link no longer works", async () => {
    window.history.replaceState(null, "", "/entrar-na-equipe#token=old");
    fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/me": () => ({ status: 401, body: { error: "not_signed_in" } }),
      "POST /api/join/check": () => ({ status: 404, body: { error: "join_link_invalid" } }),
    });
    renderAt("/entrar-na-equipe#token=old");
    expect(await screen.findByRole("heading", { name: "Este link não funciona mais" })).toBeInTheDocument();
  });
});

describe("confirming the email", () => {
  const caio = { ...ME, name: "Caio Reis", email: "caio@gmail.com", role: "member", email_confirmed: false };

  it("shows only the confirmation until it's done, whatever the address", async () => {
    api({}, { "GET /api/me": () => ({ body: caio }) });
    renderAt("/configuracoes/equipe");
    expect(await screen.findByRole("heading", { name: "Confirme seu e-mail" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Projetos" })).not.toBeInTheDocument();
  });

  it("sends a new code, and says when it can't", async () => {
    let failing = false;
    api(
      {},
      {
        "GET /api/me": () => ({ body: caio }),
        "POST /api/me/email-code/resend": () => (failing ? { status: 503, body: { error: "email_not_sent" } } : { status: 204 }),
      },
    );
    renderAt("/");
    await userEvent.click(await screen.findByRole("button", { name: "Reenviar código" }));
    expect(await screen.findByText("Enviamos um novo código para caio@gmail.com.")).toBeInTheDocument();
    failing = true;
    await userEvent.click(screen.getByRole("button", { name: "Reenviar código" }));
    expect(await screen.findByText(/Não foi possível enviar o e-mail/)).toBeInTheDocument();
    expect(screen.queryByText("Enviamos um novo código para caio@gmail.com.")).not.toBeInTheDocument();
  });

  it("corrects a mistyped address, and the code goes there", async () => {
    const sent = api(
      {},
      {
        "GET /api/me": () => ({ body: caio }),
        "PUT /api/me/email": (body: unknown) => ({ body: { ...caio, email: (body as { email: string }).email } }),
      },
    );
    renderAt("/");
    await userEvent.click(await screen.findByRole("button", { name: "Corrigir e-mail" }));
    const field = screen.getByLabelText("E-mail");
    await userEvent.clear(field);
    await userEvent.type(field, "caio@hotmail.com");
    await userEvent.click(screen.getByRole("button", { name: "Salvar e enviar código" }));
    expect(await screen.findByText(/código de 6 dígitos para caio@hotmail.com/)).toBeInTheDocument();
    expect(screen.getByText("Enviamos um novo código para caio@hotmail.com.")).toBeInTheDocument();
    expect(sent.find((r) => r.path === "/api/me/email")?.body).toEqual({ email: "caio@hotmail.com" });
  });

  it("after a correction whose email couldn't go, shows the new address it was saved as", async () => {
    let email = caio.email;
    api(
      {},
      {
        "GET /api/me": () => ({ body: { ...caio, email } }),
        "PUT /api/me/email": (body: unknown) => {
          email = (body as { email: string }).email; // saved, but not sent
          return { status: 503, body: { error: "email_not_sent" } };
        },
      },
    );
    renderAt("/");
    await userEvent.click(await screen.findByRole("button", { name: "Corrigir e-mail" }));
    const field = screen.getByLabelText("E-mail");
    await userEvent.clear(field);
    await userEvent.type(field, "caio@hotmail.com");
    await userEvent.click(screen.getByRole("button", { name: "Salvar e enviar código" }));
    expect(await screen.findByText(/Não foi possível enviar o e-mail/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(await screen.findByText(/código de 6 dígitos para caio@hotmail.com/)).toBeInTheDocument();
  });

  it("the email's link confirms with a press, not on opening", async () => {
    window.history.replaceState(null, "", "/confirmar-email#token=tok");
    const sent = fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/me": () => ({ status: 401, body: { error: "not_signed_in" } }),
      "POST /api/email-confirmation": () => ({ status: 204 }),
    });
    renderAt("/confirmar-email#token=tok");
    await userEvent.click(await screen.findByRole("button", { name: "Confirmar meu e-mail" }));
    expect(await screen.findByRole("heading", { name: "E-mail confirmado" })).toBeInTheDocument();
    expect(sent.filter((r) => r.path === "/api/email-confirmation").map((r) => r.body)).toEqual([{ token: "tok" }]);
  });

  it("says when the email's link no longer works", async () => {
    window.history.replaceState(null, "", "/confirmar-email#token=old");
    fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/me": () => ({ status: 401, body: { error: "not_signed_in" } }),
      "POST /api/email-confirmation": () => ({ status: 404, body: { error: "link_invalid" } }),
    });
    renderAt("/confirmar-email#token=old");
    await userEvent.click(await screen.findByRole("button", { name: "Confirmar meu e-mail" }));
    expect(await screen.findByRole("heading", { name: "Este link não funciona mais" })).toBeInTheDocument();
  });

  it("the team shows who hasn't confirmed yet", async () => {
    const caioMember = { id: "u-3", name: "Caio Reis", email: "caio@gmail.com", role: "member", status: "unconfirmed", me: false };
    api({ members: [DONA, caioMember] });
    renderAt("/configuracoes/equipe");
    const row = (await screen.findByText("caio@gmail.com")).closest("li")!;
    expect(within(row).getByText("E-mail não confirmado")).toBeInTheDocument();
  });
});
