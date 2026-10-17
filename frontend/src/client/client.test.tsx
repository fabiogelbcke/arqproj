import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, TENANT } from "../test/render";
import { ClientApp, slugFromPath } from "./ClientApp";
import { detailValue, googleCalendarLink, meetingWhen, paragraphs, type Page } from "./format";
import { shownFiles, sortFiles } from "./FileTools";

const PAGE: Page = {
  office: { name: "Alinea", logo_url: null },
  locale: "pt-BR",
  timezone: "America/Sao_Paulo",
  name: "Casa Jardim",
  client_name: "Família Oliveira",
  project_type: "Projeto Arquitetônico",
  project_type_key: "architecture",
  description: "Residência no alto.\n- Concreto aparente\n- Brises de madeira",
  cover_url: null,
  completed: false,
  current_position: 2,
  last_update: "2026-10-15T23:30:00Z", // 20:30 in São Paulo: still the 15th there
  details: [
    { key: "site_area", label: "Área do terreno", type: "area", value: 1240 },
    { key: "start_date", label: "Início", type: "date", value: "2026-03-02" },
  ],
  stages: [
    { position: 1, title: "Briefing", about: "Necessidades e orçamento.", notes: "" },
    { position: 2, title: "Levantamento", about: "Análise do terreno.", notes: "Medidas conferidas." },
    { position: 3, title: "Estudo Preliminar", about: null, notes: "" },
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
    expect(await within(current).findByRole("button", { name: "Abrir Planta.pdf" })).toBeInTheDocument();
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
    const draft = { ...PAGE, staff: { project_id: "p-1", status: "draft" as const, row_version: 1 } };
    let published = false;
    window.history.pushState({}, "", "/casa-jardim");
    const sent = fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/me": () => ({ body: { csrf_token: "csrf-9" } }),
      "GET /api/pages/casa-jardim": () => ({
        body: published ? { ...draft, staff: { project_id: "p-1", status: "active", row_version: 2 } } : draft,
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

describe("edit mode", () => {
  function asStaff(extra: Record<string, (body: unknown) => { status?: number; body?: unknown }> = {}) {
    let version = 4;
    window.history.pushState({}, "", "/casa-jardim");
    const sent = fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/me": () => ({ body: { csrf_token: "csrf-9" } }),
      "GET /api/pages/casa-jardim": () => ({
        body: { ...PAGE, staff: { project_id: "p-1", status: "active", row_version: version } },
      }),
      ...extra,
    });
    render(<ClientApp />);
    return { sent, bump: () => (version += 1) };
  }

  async function startEditing() {
    const bar = await screen.findByRole("navigation", { name: "Ferramentas do escritório" });
    await waitFor(() => expect(within(bar).getByRole("button", { name: "Editar" })).toBeEnabled());
    await userEvent.click(within(bar).getByRole("button", { name: "Editar" }));
  }

  it("shows no edit controls until staff switch to Editar", async () => {
    asStaff();
    await screen.findByRole("navigation", { name: "Ferramentas do escritório" });
    expect(screen.queryByRole("button", { name: "Editar descrição" })).toBeNull();
    await startEditing();
    expect(screen.getByRole("button", { name: "Editar descrição" })).toBeInTheDocument();
  });

  it("saves the description with the page's row version", async () => {
    const { sent } = asStaff({ "PATCH /api/projects/p-1/content": () => ({ status: 204 }) });
    await startEditing();
    await userEvent.click(screen.getByRole("button", { name: "Editar descrição" }));
    const box = await screen.findByLabelText("Descrição");
    await userEvent.clear(box);
    await userEvent.type(box, "Casa nova.");
    await userEvent.click(screen.getByRole("button", { name: "Salvar" }));
    expect(await screen.findByText("Salvo.")).toBeInTheDocument();
    const request = sent.find((r) => r.method === "PATCH");
    expect(request?.body).toEqual({ row_version: 4, description: "Casa nova." });
    expect(request?.headers.get("X-CSRF-Token")).toBe("csrf-9");
  });

  it("renames the stage now on that row, after stages moved", async () => {
    let moved = false;
    const stages = () =>
      (moved ? [PAGE.stages[1]!, PAGE.stages[0]!, PAGE.stages[2]!] : PAGE.stages).map((stage, i) => ({
        ...stage,
        position: i + 1,
      }));
    window.history.pushState({}, "", "/casa-jardim");
    fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/me": () => ({ body: { csrf_token: "csrf-9" } }),
      "GET /api/pages/casa-jardim": () => ({
        body: { ...PAGE, stages: stages(), staff: { project_id: "p-1", status: "active", row_version: 4 } },
      }),
      "POST /api/projects/p-1/stages/1/move": () => {
        moved = true;
        return { status: 204 };
      },
    });
    render(<ClientApp />);
    await startEditing();
    await userEvent.click(await screen.findByRole("button", { name: "Mover Briefing para baixo" }));
    await userEvent.click(await screen.findByRole("button", { name: "Renomear etapa Levantamento" }));
    expect(screen.getByLabelText("Nome da etapa")).toHaveValue("Levantamento");
  });

  it.each([
    ["active", true],
    ["draft", false],
  ])("at the last stage, offers Concluir projeto only to an active project (%s)", async (status, offered) => {
    window.history.pushState({}, "", "/casa-jardim");
    fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/me": () => ({ body: { csrf_token: "csrf-9" } }),
      "GET /api/pages/casa-jardim": () => ({
        body: { ...PAGE, current_position: PAGE.stages.length, staff: { project_id: "p-1", status, row_version: 4 } },
      }),
    });
    render(<ClientApp />);
    await startEditing();
    expect(await screen.findByText(/Estudo Preliminar/, { selector: ".rail__now p" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Concluir projeto" }) !== null).toBe(offered);
  });

  it("changes the project type with the details, only when it changed", async () => {
    const { sent } = asStaff({
      "GET /api/detail-types": () => ({ body: [] }),
      "GET /api/project-types": () => ({
        body: {
          types: [
            { key: "architecture", label: "Projeto Arquitetônico" },
            { key: "renovation", label: "Projeto de Reforma" },
          ],
        },
      }),
      "PATCH /api/projects/p-1/content": () => ({ status: 204 }),
    });
    await startEditing();
    await userEvent.click(screen.getByRole("button", { name: "Editar informações" }));
    const type = await screen.findByLabelText("Tipo de projeto");
    await screen.findByRole("option", { name: "Projeto de Reforma" });
    await userEvent.selectOptions(type, "renovation");
    await userEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await screen.findByText("Salvo.");
    expect(sent.find((r) => r.method === "PATCH")?.body).toMatchObject({ project_type: "renovation" });
  });

  it("doesn't offer Editar on an archived project", async () => {
    window.history.pushState({}, "", "/casa-jardim");
    fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/me": () => ({ body: { csrf_token: "csrf-9" } }),
      "GET /api/pages/casa-jardim": () => ({
        body: { ...PAGE, staff: { project_id: "p-1", status: "archived", row_version: 4 } },
      }),
    });
    render(<ClientApp />);
    const bar = await screen.findByRole("navigation", { name: "Ferramentas do escritório" });
    const editar = within(bar).getByRole("button", { name: "Editar" });
    expect(editar).toBeDisabled();
    expect(editar).toHaveAttribute("title", expect.stringContaining("desarquive"));
  });

  function stagePage(stages: () => Page["stages"], version: () => number, extra: Parameters<typeof fakeApi>[0] = {}) {
    window.history.pushState({}, "", "/casa-jardim");
    fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/me": () => ({ body: { csrf_token: "csrf-9" } }),
      "GET /api/pages/casa-jardim": () => ({
        body: { ...PAGE, stages: stages(), staff: { project_id: "p-1", status: "active", row_version: version() } },
      }),
      ...extra,
    });
    render(<ClientApp />);
  }

  it("closes the remove confirmation once the stage is gone", async () => {
    let removed = false;
    stagePage(
      () => (removed ? [PAGE.stages[0]!, PAGE.stages[2]!] : PAGE.stages).map((s, i) => ({ ...s, position: i + 1 })),
      () => (removed ? 5 : 4),
      {
        "DELETE /api/projects/p-1/stages/2": () => {
          removed = true;
          return { status: 204 };
        },
      },
    );
    await startEditing();
    await userEvent.click(await screen.findByRole("button", { name: "Remover etapa Levantamento" }));
    const confirm = screen.getByRole("group", { name: "Remover etapa Levantamento" });
    await userEvent.click(within(confirm).getByRole("button", { name: "Remover" }));
    // The row now shows Estudo Preliminar: no confirmation waits one click from removing it.
    await screen.findByRole("button", { name: "Remover etapa Estudo Preliminar" });
    expect(screen.queryByRole("group", { name: /Remover etapa/ })).toBeNull();
  });

  it("keeps stage controls off until the page shows the change", async () => {
    let moved = false;
    stagePage(
      () => PAGE.stages,
      () => 4, // the reload hasn't brought the new version yet
      {
        "POST /api/projects/p-1/stages/1/move": () => {
          moved = true;
          return { status: 204 };
        },
      },
    );
    await startEditing();
    await userEvent.click(await screen.findByRole("button", { name: "Mover Briefing para baixo" }));
    expect(moved).toBe(true);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Mover Levantamento para baixo" })).toBeDisabled(),
    );
  });

  describe("uploads and hiding (A31)", () => {
    const FILES = {
      stages: [
        { position: 1, groups: [] },
        {
          position: 2,
          groups: [{ folder: null, files: [{ key: "k1", name: "Planta.pdf", kind: "pdf", size: 2048, modified_at: "2026-10-10T12:00:00Z" }] }],
        },
        { position: 3, groups: [] },
      ],
    };

    // The browser's own PUT to the upload address: XMLHttpRequest, for progress.
    class FakeXhr {
      static sent: { method: string; url: string; body: unknown }[] = [];
      static answer = 200; // Google's answer to every PUT
      responseText = "";
      upload: { onprogress?: (event: { lengthComputable: boolean; loaded: number; total: number }) => void } = {};
      status = 0;
      onload?: () => void;
      onerror?: () => void;
      private method = "";
      private url = "";
      open(method: string, url: string) {
        this.method = method;
        this.url = url;
      }
      setRequestHeader() {}
      send(body: File) {
        FakeXhr.sent.push({ method: this.method, url: this.url, body });
        this.upload.onprogress?.({ lengthComputable: true, loaded: body.size, total: body.size });
        this.status = FakeXhr.answer;
        this.responseText = this.status >= 400 ? "storageQuotaExceeded" : "";
        setTimeout(() => this.onload?.());
      }
    }

    function asEditor(extra: Parameters<typeof fakeApi>[0] = {}) {
      FakeXhr.sent = [];
      FakeXhr.answer = 200;
      vi.stubGlobal("XMLHttpRequest", FakeXhr);
      return asStaff({ "GET /api/pages/casa-jardim/files": () => ({ body: FILES }), ...extra });
    }

    it("sends a chosen file straight to the address the app opened, then lists again", async () => {
      const { sent } = asEditor({
        "POST /api/projects/p-1/stages/2/uploads": () => ({ body: { upload_url: "https://upload.example/s1" } }),
      });
      await startEditing();
      const stage = screen.getByRole("region", { name: "Levantamento" });
      const file = new File(["%PDF"], "Corte.pdf", { type: "application/pdf" });
      await userEvent.upload(await within(stage).findByLabelText("escolha no computador"), file);
      expect(await screen.findByText("Arquivo enviado.")).toBeInTheDocument();
      expect(sent.find((r) => r.method === "POST")?.body).toEqual({
        row_version: 4,
        name: "Corte.pdf",
        size: 4,
        mime_type: "application/pdf",
      });
      expect(FakeXhr.sent).toEqual([{ method: "PUT", url: "https://upload.example/s1", body: file }]);
      await waitFor(() =>
        expect(sent.filter((r) => r.method === "GET" && r.path === "/api/pages/casa-jardim/files").length).toBe(2),
      );
    });

    it("reports a send that failed for good, and shows the support code", async () => {
      const { sent } = asEditor({
        "POST /api/projects/p-1/stages/2/uploads": () => ({ body: { upload_url: "https://upload.example/s1" } }),
        "POST /api/projects/p-1/stages/2/uploads/failed": () => ({
          status: 502,
          body: { error: "upload_failed" },
          headers: { "X-Request-ID": "ref-77" },
        }),
      });
      FakeXhr.answer = 403; // e.g. the office's Drive is full
      await startEditing();
      const stage = screen.getByRole("region", { name: "Levantamento" });
      await userEvent.upload(
        await within(stage).findByLabelText("escolha no computador"),
        new File(["%PDF"], "Corte.pdf", { type: "application/pdf" }),
      );
      expect(await within(stage).findByRole("alert")).toHaveTextContent(
        "Não foi possível enviar o arquivo. Tente de novo; se continuar, fale com o suporte. Código de suporte: ref-77",
      );
      expect(sent.find((r) => r.path.endsWith("/uploads/failed"))?.body).toEqual({
        name: "Corte.pdf",
        size: 4,
        status: 403,
        detail: "storageQuotaExceeded",
      });
    });

    it("says a file over 100 MB is too large, without opening an upload", async () => {
      const { sent } = asEditor();
      await startEditing();
      const stage = screen.getByRole("region", { name: "Levantamento" });
      const big = new File(["x"], "Video.mp4", { type: "video/mp4" });
      Object.defineProperty(big, "size", { value: 101 * 1024 * 1024 });
      await userEvent.upload(await within(stage).findByLabelText("escolha no computador"), big);
      expect(await within(stage).findByRole("alert")).toHaveTextContent("até 100 MB");
      expect(sent.some((r) => r.method === "POST")).toBe(false);
      expect(FakeXhr.sent).toEqual([]);
    });

    it("hides a file from the client from its menu", async () => {
      const { sent } = asEditor({ "POST /api/pages/casa-jardim/files/k1/hide": () => ({ status: 204 }) });
      await startEditing();
      await userEvent.click(await screen.findByRole("button", { name: "Ações para Planta.pdf" }));
      await userEvent.click(screen.getByRole("menuitem", { name: /Ocultar do cliente/ }));
      expect(await screen.findByText(/não aparece mais para o cliente/)).toBeInTheDocument();
      expect(sent.some((r) => r.method === "POST" && r.path.endsWith("/k1/hide"))).toBe(true);
    });

    it("explains how to hide a file not sent through the site", async () => {
      asEditor({
        "POST /api/pages/casa-jardim/files/k1/hide": () => ({ status: 409, body: { error: "file_not_ours" } }),
      });
      await startEditing();
      await userEvent.click(await screen.findByRole("button", { name: "Ações para Planta.pdf" }));
      await userEvent.click(screen.getByRole("menuitem", { name: /Ocultar do cliente/ }));
      expect(await screen.findByText(/renomeie-o na pasta da etapa começando com _/)).toBeInTheDocument();
    });

    it("shows neither to someone viewing as the client", async () => {
      asEditor();
      await screen.findByRole("button", { name: "Abrir Planta.pdf" });
      expect(screen.queryByLabelText("escolha no computador")).toBeNull();
      expect(screen.queryByRole("button", { name: "Ações para Planta.pdf" })).toBeNull();
    });
  });

  it("says when someone else changed the project meanwhile", async () => {
    asStaff({ "PUT /api/projects/p-1/stages/2/notes": () => ({ status: 409, body: { error: "project_changed" } }) });
    await startEditing();
    await userEvent.click(screen.getByRole("button", { name: "Editar recado" }));
    await userEvent.click(await screen.findByRole("button", { name: "Salvar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("alterado por outra pessoa");
  });

  it("schedules the meeting on the office's clock", async () => {
    const { sent } = asStaff({ "PUT /api/projects/p-1/meeting": () => ({ status: 204 }) });
    await startEditing();
    await userEvent.click(screen.getByRole("button", { name: "Editar reunião" }));
    // The existing meeting (19:00 UTC) shows as 16:00, São Paulo's time.
    expect(await screen.findByLabelText("Início")).toHaveValue("16:00");
    expect(screen.getByLabelText("Data")).toHaveValue("2026-10-21");
    await userEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await screen.findByText("Salvo.");
    expect(sent.find((r) => r.method === "PUT")?.body).toMatchObject({
      row_version: 4,
      title: "Apresentação",
      day: "2026-10-21",
      start: "16:00",
      end: "17:00",
    });
  });
});

describe("formatting", () => {
  it("reads the page from the address", () => {
    expect(slugFromPath("/casa-jardim")).toBe("casa-jardim");
    expect(slugFromPath("/casa-jardim/")).toBe("casa-jardim");
  });

  it("shows areas, dates and text as the design does", () => {
    expect(detailValue({ key: "a", label: "Área", type: "area", value: 148.5 }, "pt-BR")).toBe("148,5 m²");
    expect(detailValue({ key: "d", label: "Início", type: "date", value: "2026-03-02" }, "pt-BR")).toBe("02/03/2026");
    expect(detailValue({ key: "l", label: "Local", type: "text", value: "Florianópolis" }, "pt-BR")).toBe("FLORIANÓPOLIS");
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


describe("the page's file tools", () => {
  const file = (key: string, name: string, kind: string, at: string) =>
    ({ key, name, kind, size: 10, modified_at: at }) as never;
  const FILES = {
    stages: [
      { position: 1, groups: [{ folder: null, files: [file("a", "Programa.pdf", "pdf", "2026-10-01T12:00:00Z")] }] },
      {
        position: 2,
        groups: [
          {
            folder: null,
            files: [
              file("b", "Planta baixa.pdf", "pdf", "2026-10-05T12:00:00Z"),
              file("c", "Implantação.dwg", "other", "2026-10-09T12:00:00Z"),
              file("d", "Terreno.jpg", "image", "2026-10-02T12:00:00Z"),
            ],
          },
        ],
      },
      { position: 3, groups: [] },
    ],
    updates: [],
  };

  it("sorts by date, newest first, by type, or by name", () => {
    const files = FILES.stages[1]!.groups[0]!.files as never[];
    const names = (sort: "updated" | "type" | "name") => sortFiles(files, sort).map((f: { name: string }) => f.name);
    expect(names("updated")).toEqual(["Implantação.dwg", "Planta baixa.pdf", "Terreno.jpg"]);
    expect(names("type")).toEqual(["Implantação.dwg", "Terreno.jpg", "Planta baixa.pdf"]);
    expect(names("name")).toEqual(["Implantação.dwg", "Planta baixa.pdf", "Terreno.jpg"]);
  });

  it("finds files by name or by their stage, without minding accents or case", () => {
    const stage = FILES.stages[1] as never;
    const prefs = { type: "all", sort: "name", view: "grid" } as const;
    expect(shownFiles(stage, "Levantamento", "implantacao", prefs).count).toBe(1);
    expect(shownFiles(stage, "Levantamento", "LEVANTAMENTO", prefs).count).toBe(3);
    expect(shownFiles(stage, "Levantamento", "", { ...prefs, type: "pdf" }).count).toBe(1);
    expect(shownFiles(stage, "Levantamento", "", { ...prefs, type: "dwg" }).count).toBe(1);
  });

  it("searching hides stages without a match and says how many were found", async () => {
    localStorage.clear();
    at("/casa-jardim", {
      "GET /api/pages/casa-jardim": () => ({ body: PAGE }),
      "GET /api/pages/casa-jardim/files": () => ({ body: FILES }),
    });
    await userEvent.type(await screen.findByLabelText("Pesquisar arquivos"), "baixa"); // "planta" would also find "Implantação"
    expect(screen.getByText("1 arquivo encontrado")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Levantamento" })).toBeVisible();
    expect(screen.queryByRole("region", { name: "Briefing" })).toBeNull(); // hidden
  });

  it("switches to a list, and remembers it", async () => {
    localStorage.clear();
    at("/casa-jardim", {
      "GET /api/pages/casa-jardim": () => ({ body: PAGE }),
      "GET /api/pages/casa-jardim/files": () => ({ body: FILES }),
    });
    await userEvent.click(await screen.findByRole("button", { name: "Visualizar em lista" }));
    expect(document.querySelector(".files")).toHaveAttribute("data-view", "list");
    expect(JSON.parse(localStorage.getItem("file-prefs")!)).toMatchObject({ view: "list" });
  });

  it("opens a file's preview, with its actions", async () => {
    at("/casa-jardim", {
      "GET /api/pages/casa-jardim": () => ({ body: PAGE }),
      "GET /api/pages/casa-jardim/files": () => ({ body: FILES }),
    });
    await userEvent.click(await screen.findByRole("button", { name: "Abrir Terreno.jpg" }));
    const preview = screen.getByRole("dialog", { name: "Terreno.jpg" });
    expect(within(preview).getByRole("img", { name: "Terreno.jpg" })).toHaveAttribute(
      "src",
      "/api/pages/casa-jardim/files/d?inline=true",
    );
    expect(within(preview).getByRole("link", { name: "Abrir original" })).toHaveAttribute(
      "href",
      "/api/pages/casa-jardim/files/d?inline=true",
    );
    await userEvent.click(within(preview).getByRole("button", { name: "Enviar" }));
    const whatsapp = within(preview).getByRole("link", { name: "WhatsApp" });
    // The page's address, not the file's (which works only for a while).
    expect(decodeURIComponent(whatsapp.getAttribute("href")!)).toContain(`${window.location.origin}/casa-jardim`);
    await userEvent.click(within(preview).getByRole("button", { name: "Fechar" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
