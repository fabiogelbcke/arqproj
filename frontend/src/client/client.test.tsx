import { render, screen, waitFor, within } from "@testing-library/react";
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
    await waitFor(() => expect(document.title).toBe("Casa Jardim · Alinea")); // set after drawing
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

  it("asks for the password on a protected page, then shows it", async () => {
    let unlocked = false;
    let tries = 0;
    window.history.pushState({}, "", "/refugio");
    const sent = fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/pages/refugio": () =>
        unlocked ? { body: { ...PAGE, name: "Refúgio" } } : { status: 403, body: { error: "page_locked" } },
      "POST /api/pages/refugio/unlock": (body: unknown) => {
        tries += 1;
        if ((body as { password: string }).password !== "certa") return { status: 401, body: { error: "wrong_page_password" } };
        unlocked = true;
        return { status: 204 };
      },
    });
    render(<ClientApp />);
    expect(await screen.findByRole("heading", { name: "Página protegida" })).toBeInTheDocument();
    expect(screen.queryByText("Refúgio")).toBeNull();
    await userEvent.type(screen.getByLabelText("Senha"), "errada");
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Senha incorreta.");
    await userEvent.clear(screen.getByLabelText("Senha"));
    await userEvent.type(screen.getByLabelText("Senha"), "certa");
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Refúgio" })).toBeInTheDocument();
    expect(tries).toBe(2);
    expect(sent.filter((r) => r.method === "POST").map((r) => r.body)).toEqual([
      { password: "errada" },
      { password: "certa" },
    ]);
  });

  it("tells a device to wait after too many wrong passwords", async () => {
    at("/refugio", {
      "GET /api/pages/refugio": () => ({ status: 403, body: { error: "page_locked" } }),
      "POST /api/pages/refugio/unlock": () => ({ status: 429, body: { error: "too_many_attempts" } }),
    });
    await userEvent.type(await screen.findByLabelText("Senha"), "qualquer");
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Tente de novo em 15 minutos.");
  });

  it("shows any other failure with its support code, never the server's words", async () => {
    at("/casa", {
      "GET /api/pages/casa": () => ({ status: 500, body: { error: "boom", detail: "Traceback…" } }),
    });
    expect(await screen.findByRole("heading", { name: "Algo deu errado. Tente de novo em instantes." })).toBeInTheDocument();
    expect(screen.queryByText(/Traceback/)).toBeNull();
  });
});

describe("the files", () => {
  it("shows each stage's files, its subfolders as groups, and how many", async () => {
    at("/casa-jardim", {
      "GET /api/pages/casa-jardim": () => ({ body: PAGE }),
      "GET /api/pages/casa-jardim/files": () => ({
        body: {
          stages: [
            { position: 1, groups: [], unavailable: true },
            {
              position: 2,
              groups: [
                { folder: null, files: [{ key: "k1", name: "Planta.pdf", kind: "pdf", size: 2048, modified_at: "2026-10-10T12:00:00Z" }] },
                { folder: "Fotos", files: [{ key: "k2", name: "Terreno.jpg", kind: "image", size: 10, modified_at: "2026-10-11T12:00:00Z" }] },
              ],
            },
            { position: 3, groups: [] },
          ],
        },
      }),
    });
    const current = await screen.findByRole("region", { name: "Levantamento" });
    expect(await within(current).findByRole("link", { name: "Abrir Planta.pdf" })).toHaveAttribute(
      "href",
      "/api/pages/casa-jardim/files/k1?inline=true",
    );
    expect(within(current).getByRole("heading", { name: "Fotos" })).toBeInTheDocument();
    expect(within(current).getByText("02 arquivos")).toBeInTheDocument();
    expect(within(current).getByText("2 KB, 10/10/2026")).toBeInTheDocument();
    const first = screen.getByRole("region", { name: "Briefing" });
    expect(within(first).getByText(/Não foi possível carregar os arquivos/)).toBeInTheDocument();
    const third = screen.getByRole("region", { name: "Estudo Preliminar" });
    expect(within(third).getByText("Ainda sem arquivos nesta etapa.")).toBeInTheDocument();
  });
});

describe("files that can't be listed", () => {
  it("says so in every stage, with the support code, instead of staying blank", async () => {
    at("/casa-jardim", {
      "GET /api/pages/casa-jardim": () => ({ body: PAGE }),
      "GET /api/pages/casa-jardim/files": () => ({
        status: 500,
        body: { error: "unexpected" },
        headers: { "X-Request-ID": "ref42" },
      }),
    });
    const current = await screen.findByRole("region", { name: "Levantamento" });
    expect(await within(current).findByText(/Não foi possível carregar os arquivos.*Código de suporte: ref42/)).toBeInTheDocument();
  });
});

describe("the staff bar", () => {
  it("is only there for the office's staff", async () => {
    at("/casa-jardim", { "GET /api/pages/casa-jardim": () => ({ body: PAGE }) });
    await screen.findByRole("heading", { level: 1, name: "Casa Jardim" });
    expect(screen.queryByRole("navigation", { name: "Ferramentas do escritório" })).toBeNull();
  });

  it("publishes a draft, with the CSRF token, and shows it as published", async () => {
    const draft = { ...PAGE, staff: { project_id: "p-1", status: "draft" as const } };
    let published = false;
    window.history.pushState({}, "", "/casa-jardim");
    const sent = fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/me": () => ({ body: { csrf_token: "csrf-9" } }),
      "GET /api/pages/casa-jardim": () => ({
        body: published ? { ...draft, staff: { project_id: "p-1", status: "active" } } : draft,
      }),
      "POST /api/projects/p-1/publish": () => {
        published = true;
        return { body: {} };
      },
    });
    render(<ClientApp />);
    const bar = await screen.findByRole("navigation", { name: "Ferramentas do escritório" });
    expect(within(bar).getByText("Rascunho, só você vê")).toBeInTheDocument();
    await userEvent.click(within(bar).getByRole("button", { name: "Publicar" }));
    expect(await screen.findByText("Publicado. O cliente já pode abrir o link.")).toBeInTheDocument();
    expect(await within(bar).findByText("Publicado")).toBeInTheDocument();
    expect(within(bar).queryByRole("button", { name: "Publicar" })).toBeNull();
    expect(sent.find((r) => r.method === "POST")?.headers.get("X-CSRF-Token")).toBe("csrf-9");
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
