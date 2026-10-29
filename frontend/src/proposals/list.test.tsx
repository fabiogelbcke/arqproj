import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, ME, renderAt, TENANT } from "../test/render";
import type { ProposalRow } from "./proposals";

afterEach(() => vi.unstubAllGlobals());

const WITH_PROPOSALS = { ...ME, features: ["proposals"] };

function row(changes: Partial<ProposalRow>): ProposalRow {
  return {
    project_id: "p-1",
    name: "Casa do Lago",
    client_name: "Família Souza",
    slug: "casa-do-lago",
    state: "open",
    version: 2,
    saved_at: "2026-10-28T15:00:00Z",
    fee: 2_900_000,
    created_at: "2026-10-27T12:00:00Z",
    row_version: 4,
    ...changes,
  };
}

const ROWS = [
  row({}),
  row({ project_id: "p-2", name: "Casa Nova", slug: "casa-nova", version: null, saved_at: null, fee: null }),
  row({ project_id: "p-3", name: "Casa Jardim", slug: "casa-jardim", state: "accepted" }),
  row({ project_id: "p-4", name: "Casa Velha", slug: "casa-velha", state: "declined" }),
];

function api(extra = {}) {
  return fakeApi({
    "GET /api/tenant": () => ({ body: TENANT }),
    "GET /api/me": () => ({ body: WITH_PROPOSALS }),
    "GET /api/proposals": () => ({ body: ROWS }),
    "GET /api/onboarding": () => ({ body: { storage_connected: true, office_details: true, has_project: true } }),
    ...extra,
  });
}

describe("the Propostas tab (A42)", () => {
  it("is a tab beside Projetos only where proposals are switched on", async () => {
    api({ "GET /api/projects": () => ({ body: [] }) });
    renderAt("/");
    const nav = await screen.findByRole("navigation", { name: "Painel" });
    expect(await within(nav).findByRole("link", { name: "Propostas" })).toHaveAttribute("href", "/propostas");
  });

  it("isn't there, nor its address, where proposals are off", async () => {
    api({ "GET /api/me": () => ({ body: ME }), "GET /api/projects": () => ({ body: [] }) });
    renderAt("/propostas");
    expect(await screen.findByRole("heading", { name: "Página não encontrada" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Propostas" })).toBeNull();
  });

  it("lists open, accepted and declined proposals, each opening where it should", async () => {
    api();
    renderAt("/propostas");
    const open = await screen.findByRole("region", { name: /Ativas/ });
    // Saved: its page, as the client sees it. Never saved: the generator, to write it.
    expect(within(open).getByRole("link", { name: /Casa do Lago/ })).toHaveAttribute("href", "/casa-do-lago");
    expect(within(open).getByRole("link", { name: /Casa Nova/ })).toHaveAttribute("href", "/projetos/p-2/proposta");
    expect(within(open).getByText("Ainda não salva")).toBeInTheDocument();
    expect(within(open).getAllByText("R$ 29.000,00").length).toBe(1);
    expect(within(screen.getByRole("region", { name: /Aceitas/ })).getByRole("link", { name: /Casa Jardim/ })).toHaveAttribute(
      "href",
      "/casa-jardim",
    );
    expect(within(screen.getByRole("region", { name: /Recusadas/ })).getByText("Casa Velha")).toBeInTheDocument();
  });

  it("starts a new proposal from here", async () => {
    api({ "GET /api/drive": () => ({ body: { kind: "folder", writer_status: "none", reader_status: "unknown" } }) });
    renderAt("/propostas");
    await userEvent.click(await screen.findByRole("button", { name: "Nova proposta" }));
    expect(await screen.findByRole("dialog", { name: "Nova proposta" })).toBeInTheDocument();
  });

  it("marks one declined from its menu, and reopens a declined one", async () => {
    const sent = api({ "PATCH /api/projects/p-1": () => ({ body: {} }), "PATCH /api/projects/p-4": () => ({ body: {} }) });
    renderAt("/propostas");
    await userEvent.click(await screen.findByRole("button", { name: "Ações de Casa do Lago" }));
    await userEvent.click(within(await screen.findByRole("menu")).getByRole("menuitem", { name: "Marcar como recusada" }));
    await waitFor(() => expect(sent.some((r) => r.path === "/api/projects/p-1")).toBe(true));
    expect(sent.find((r) => r.path === "/api/projects/p-1")!.body).toEqual({ status: "archived", row_version: 4 });

    await userEvent.click(screen.getByRole("button", { name: "Ações de Casa Velha" }));
    await userEvent.click(within(await screen.findByRole("menu")).getByRole("menuitem", { name: "Reabrir proposta" }));
    await waitFor(() => expect(sent.some((r) => r.path === "/api/projects/p-4")).toBe(true));
    expect(sent.find((r) => r.path === "/api/projects/p-4")!.body).toEqual({ status: "proposal", row_version: 4 });
  });
});
