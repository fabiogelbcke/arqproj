import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi } from "../test/render";
import { OfficeSignupApp, suggestedAddress } from "./OfficeSignup";

const OWNER_URL = "https://estudio-ipe.myunio.app/painel/entrar-na-equipe#token=dono";

/** Opens /criar-escritorio#token=…, with the link good and "ipe-x" taken. */
function openLink(token = "convite", extra: Parameters<typeof fakeApi>[0] = {}) {
  window.history.replaceState(null, "", `/criar-escritorio#token=${token}`);
  const assign = vi.fn();
  vi.stubGlobal("location", { ...window.location, assign });
  const cleared = vi.spyOn(window.history, "replaceState");
  const sent = fakeApi({
    "POST /api/office-signup/check": (body) => {
      const { address } = body as { address?: string };
      return { body: { domain: "myunio.app", address_free: address === undefined ? null : address !== "ipe-x" } };
    },
    "POST /api/office-signup/create": () => ({ body: { owner_url: OWNER_URL } }),
    ...extra,
  });
  render(<OfficeSignupApp />);
  return { sent, assign, cleared };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("creating an office from a link", () => {
  it("suggests the address from the name, says it's free, and goes on to the owner signup", async () => {
    const { sent, assign, cleared } = openLink();
    await userEvent.type(await screen.findByLabelText(/Nome do escritório/), "Estúdio Ipê");
    expect(screen.getByLabelText(/Endereço/)).toHaveValue("estudio-ipe");
    expect(screen.getByText(".myunio.app")).toBeInTheDocument(); // fixed beside it: the full address as it's typed
    expect(screen.getByText("11/40")).toBeInTheDocument();
    expect(await screen.findByText("Disponível")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Criar escritório" }));
    await vi.waitFor(() => expect(assign).toHaveBeenCalledWith(OWNER_URL));
    expect(sent.find((r) => r.path === "/api/office-signup/create")?.body).toEqual({
      token: "convite",
      name: "Estúdio Ipê",
      address: "estudio-ipe",
    });
    // The token left the address bar as soon as the page read it.
    expect(cleared).toHaveBeenCalledWith(window.history.state, "", "/criar-escritorio");
  });

  it("says when an address is taken and won't create until another is chosen", async () => {
    const { sent } = openLink();
    await userEvent.type(await screen.findByLabelText(/Nome do escritório/), "Ipê");
    const address = screen.getByLabelText(/Endereço/);
    await userEvent.clear(address);
    await userEvent.type(address, "ipe-x");
    expect(await screen.findByText("Esse endereço já está em uso. Escolha outro.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Criar escritório" })).toBeDisabled();
    await userEvent.type(address, "y");
    expect(await screen.findByText("Disponível")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Criar escritório" })).toBeEnabled();
    expect(sent.some((r) => r.path === "/api/office-signup/create")).toBe(false);
  });

  it("takes a whole address pasted in as just its own part", async () => {
    openLink();
    const address = await screen.findByLabelText(/Endereço/);
    await userEvent.click(address);
    await userEvent.paste("https://Estudio-Ipe.myunio.app/");
    expect(address).toHaveValue("estudio-ipe");
  });

  it("says a used or expired link no longer works, and shows no form", async () => {
    openLink("velho", {
      "POST /api/office-signup/check": () => ({ status: 404, body: { error: "signup_link_invalid" } }),
    });
    expect(await screen.findByRole("alert")).toHaveTextContent("Este link para criar um escritório não vale mais");
    expect(screen.queryByLabelText(/Nome do escritório/)).toBeNull();
  });

  it("says so when opened without a link", async () => {
    window.history.replaceState(null, "", "/criar-escritorio");
    const sent = fakeApi({});
    render(<OfficeSignupApp />);
    expect(await screen.findByRole("alert")).toHaveTextContent("não vale mais");
    expect(sent).toEqual([]);
  });

  it("turns names into plain addresses", () => {
    expect(suggestedAddress("Estúdio Ipê & Co.")).toBe("estudio-ipe-co");
    expect(suggestedAddress("  --Arq.  Conceição--  ")).toBe("arq-conceicao");
    expect(suggestedAddress("x".repeat(60))).toHaveLength(40);
  });
});
