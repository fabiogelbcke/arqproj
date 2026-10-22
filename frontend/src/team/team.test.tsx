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

describe("the shared link's page", () => {
  it("asks for a name and email, and says to check the email", async () => {
    window.history.replaceState(null, "", "/entrar-na-equipe#token=xyz");
    const sent = fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/me": () => ({ status: 401, body: { error: "not_signed_in" } }),
      "POST /api/join/check": () => ({ body: { office: "Alinea" } }),
      "POST /api/join": () => ({ status: 202 }),
    });
    renderAt("/entrar-na-equipe#token=xyz");
    expect(await screen.findByRole("heading", { name: "Entrar na equipe do Alinea" })).toBeInTheDocument();
    expect(window.location.hash).toBe(""); // the token leaves the address bar
    await userEvent.type(screen.getByLabelText("Nome"), "Caio Reis");
    await userEvent.type(screen.getByLabelText("E-mail"), "caio@gmail.com");
    await userEvent.click(screen.getByRole("button", { name: "Receber o link" }));
    expect(await screen.findByRole("heading", { name: "Confira seu e-mail" })).toBeInTheDocument();
    expect(sent.find((r) => r.path === "/api/join")?.body).toEqual({ token: "xyz", name: "Caio Reis", email: "caio@gmail.com" });
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
