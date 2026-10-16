import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, TENANT } from "../test/render";
import { ClientApp, slugFromPath } from "./ClientApp";
import { detailValue, googleCalendarLink, meetingWhen, paragraphs, type Page } from "./format";

const PAGE: Page = {
  office: { name: "Alinea", logo_url: null },
  locale: "pt-BR",
  timezone: "America/Sao_Paulo",
  name: "Casa Jardim",
  client_name: "Família Oliveira",
  project_type: "Projeto Arquitetônico",
  description: "Residência no alto.\n- Concreto aparente\n- Brises de madeira",
  cover_url: null,
  completed: false,
  current_position: 2,
  last_update: "2026-10-15T23:30:00Z", // 20:30 in São Paulo: still the 15th there
  details: [
    { label: "Área do terreno", type: "area", value: 1240 },
    { label: "Início", type: "date", value: "2026-03-02" },
  ],
  stages: [
    { title: "Briefing", about: "Necessidades e orçamento.", notes: "" },
    { title: "Levantamento", about: "Análise do terreno.", notes: "Medidas conferidas." },
    { title: "Estudo Preliminar", about: null, notes: "" },
  ],
  next_meeting: {
    title: "Apresentação",
    starts_at: "2026-10-21T19:00:00Z",
    ends_at: "2026-10-21T20:00:00Z",
    location: "Online",
    link: "https://meet.example/abc",
  },
};

function at(path: string, handlers: Record<string, () => { status?: number; body?: unknown }>) {
  window.history.pushState({}, "", path);
  fakeApi({ "GET /api/tenant": () => ({ body: TENANT }), ...handlers });
  render(<ClientApp />);
}

afterEach(() => vi.unstubAllGlobals());

describe("the client page", () => {
  it("shows the project with the current stage open", async () => {
    at("/casa-jardim", { "GET /api/pages/casa-jardim": () => ({ body: PAGE }) });
    expect(await screen.findByRole("heading", { level: 1, name: "Casa Jardim" })).toHaveTextContent("/casajardim");
    expect(screen.getByText("Medidas conferidas.")).toBeVisible(); // stage 2 is current
    expect(screen.getByText("1.240 m²")).toBeInTheDocument();
    expect(screen.getByText("15/10/2026")).toBeInTheDocument(); // the office's day
    expect(document.title).toBe("Casa Jardim · Alinea");
  });

  it("explains a stage in the project type's words", async () => {
    at("/casa-jardim", { "GET /api/pages/casa-jardim": () => ({ body: PAGE }) });
    await userEvent.click(await screen.findByRole("button", { name: "Sobre esta etapa: Briefing" }));
    expect(screen.getByText("Necessidades e orçamento.")).toBeVisible();
    // A stage without a description has no "Sobre esta etapa".
    expect(screen.queryByRole("button", { name: "Sobre esta etapa: Estudo Preliminar" })).toBeNull();
  });

  it("opens a stage from the timeline", async () => {
    at("/casa-jardim", { "GET /api/pages/casa-jardim": () => ({ body: PAGE }) });
    const timeline = await screen.findByRole("list", { name: "Etapas" });
    Element.prototype.scrollIntoView = vi.fn();
    await userEvent.click(within(timeline).getByRole("button", { name: /Estudo Preliminar/ }));
    const section = document.getElementById("stage-2")!;
    expect(section.className).toContain("is-expanded");
  });

  it("says when a page doesn't exist, in the office's language", async () => {
    at("/nada", { "GET /api/pages/nada": () => ({ status: 404, body: { error: "page_not_found" } }) });
    expect(await screen.findByRole("heading", { name: "Página não encontrada" })).toBeInTheDocument();
  });

  it("says when a page is protected, and shows nothing of it", async () => {
    at("/refugio", { "GET /api/pages/refugio": () => ({ status: 403, body: { error: "page_locked" } }) });
    expect(await screen.findByRole("heading", { name: "Página protegida" })).toBeInTheDocument();
  });

  it("shows any other failure with its support code, never the server's words", async () => {
    at("/casa", {
      "GET /api/pages/casa": () => ({ status: 500, body: { error: "boom", detail: "Traceback…" } }),
    });
    expect(await screen.findByRole("heading", { name: "Algo deu errado. Tente de novo em instantes." })).toBeInTheDocument();
    expect(screen.queryByText(/Traceback/)).toBeNull();
  });
});

describe("formatting", () => {
  it("reads the page from the address", () => {
    expect(slugFromPath("/casa-jardim")).toBe("casa-jardim");
    expect(slugFromPath("/casa-jardim/")).toBe("casa-jardim");
  });

  it("shows areas, dates and text as the design does", () => {
    expect(detailValue({ label: "Área", type: "area", value: 148.5 }, "pt-BR")).toBe("148,5 m²");
    expect(detailValue({ label: "Início", type: "date", value: "2026-03-02" }, "pt-BR")).toBe("02/03/2026");
    expect(detailValue({ label: "Local", type: "text", value: "Florianópolis" }, "pt-BR")).toBe("FLORIANÓPOLIS");
  });

  it("puts the meeting in the office's time zone", () => {
    const when = meetingWhen(PAGE.next_meeting!, "pt-BR", "America/Sao_Paulo");
    expect(when).toEqual({ day: "quarta-feira 21/10/2026", time: "16:00 – 17:00" });
  });

  it("fills in Google Calendar's new event", () => {
    const link = new URL(googleCalendarLink(PAGE.next_meeting!, "Casa Jardim", "https://a.example/casa"));
    expect(link.searchParams.get("dates")).toBe("20261021T190000Z/20261021T200000Z");
    expect(link.searchParams.get("text")).toBe("Apresentação · Casa Jardim");
    expect(link.searchParams.get("location")).toBe("Online");
  });

  it("turns '- ' lines into a list", () => {
    expect(paragraphs(PAGE.description)).toEqual([
      { kind: "p", text: "Residência no alto." },
      { kind: "ul", items: ["Concreto aparente", "Brises de madeira"] },
    ]);
  });
});
