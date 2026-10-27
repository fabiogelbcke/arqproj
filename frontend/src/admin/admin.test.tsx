import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { fakeApi } from "../test/render";
import { hostOf, slugFromHost } from "./Actions";
import { adminRoutes } from "./AdminApp";
import { officeErrorsUrl, supportCodeUrl } from "./logs";

const ME = { email: "fabio@unio.example", csrf_token: "csrf-9", logs_project: "arq-proj", logs_service: "portal" };
const ALINEA = {
  id: "4f1c2b8e-1111-4c4c-9a9a-000000000001",
  slug: "alinea",
  name: "Alinea",
  status: "active",
  created_at: "2026-10-15T12:00:00Z",
  hosts: ["alineaarquitetos.com", "alinea.myunio.app"],
  owners: 1,
  staff: 3,
  pending: 1,
  projects: { draft: 0, active: 4, completed: 1, archived: 2 },
  storage: "google",
  writer_status: "connected",
  reader_status: "ok",
  drive_account: "contato@alinea.example",
  last_activity_at: "2026-10-25T18:00:00Z",
  emails_sent: 12,
  share_links: 3,
  downloads: 7,
  team: [],
};
const NORTE = { ...ALINEA, slug: "norte", name: "Norte", hosts: ["norte.myunio.app"], writer_status: "expired", pending: 0 };

function renderAt(path: string) {
  const router = createMemoryRouter(adminRoutes, { initialEntries: [path] });
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}

describe("the operator dashboard", () => {
  it("asks to sign in with Google, and says why the last try didn't get in", async () => {
    window.history.replaceState(null, "", "/admin?entrar=negado");
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign, search: "?entrar=negado" });
    const sent = fakeApi({
      "GET /api/admin/me": () => ({ status: 401, body: { error: "not_signed_in" } }),
      "POST /api/admin/signin": () => ({ body: { url: "https://accounts.google.com/o/oauth2/v2/auth?x=1" } }),
    });
    renderAt("/");
    expect(await screen.findByRole("alert")).toHaveTextContent("Esta conta Google não tem acesso a esta área.");
    await userEvent.click(screen.getByRole("button", { name: "Entrar com Google" }));
    await vi.waitFor(() => expect(assign).toHaveBeenCalledWith("https://accounts.google.com/o/oauth2/v2/auth?x=1"));
    expect(sent.some((r) => r.path === "/api/admin/signin")).toBe(true);
    vi.unstubAllGlobals();
  });

  it("lists every office with its counts and health", async () => {
    fakeApi({
      "GET /api/admin/me": () => ({ body: ME }),
      "GET /api/admin/offices": () => ({ body: [ALINEA, NORTE] }),
    });
    renderAt("/");
    const table = await screen.findByRole("table");
    const alinea = within(table).getByRole("link", { name: "Alinea" }).closest("tr")!;
    expect(alinea).toHaveTextContent("alineaarquitetos.com"); // the primary address
    expect(alinea).toHaveTextContent("3 pessoas");
    expect(alinea).toHaveTextContent("1 pendente");
    expect(alinea).toHaveTextContent("4 em andamento");
    expect(alinea).toHaveTextContent("1 concluídos · 2 arquivados");
    expect(alinea).toHaveTextContent("Google Drive conectado");
    expect(alinea).toHaveTextContent("7 downloads");
    const norte = within(table).getByRole("link", { name: "Norte" }).closest("tr")!;
    expect(norte).toHaveTextContent("Google Drive expirado");
    expect(screen.getByText("fabio@unio.example")).toBeInTheDocument();
  });

  it("opens a support code's logs, only for a well-formed code", async () => {
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    fakeApi({ "GET /api/admin/me": () => ({ body: ME }), "GET /api/admin/offices": () => ({ body: [] }) });
    renderAt("/");
    const field = await screen.findByLabelText("Código");
    const button = screen.getByRole("button", { name: "Abrir registros" });
    await userEvent.type(field, "abc");
    expect(button).toBeDisabled();
    await userEvent.clear(field);
    await userEvent.type(field, "084014655BD7469EBEB538FC991C4E2B");
    await userEvent.click(button);
    expect(open).toHaveBeenCalledWith(supportCodeUrl({ project: "arq-proj", service: "portal" }, "084014655bd7469ebeb538fc991c4e2b"), "_blank", "noopener");
    open.mockRestore();
  });

  it("says logs are only on the published site, locally", async () => {
    fakeApi({
      "GET /api/admin/me": () => ({ body: { ...ME, logs_project: null, logs_service: null } }),
      "GET /api/admin/offices": () => ({ body: [] }),
    });
    renderAt("/");
    expect(await screen.findByText("Os registros só estão disponíveis no site publicado.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Abrir registros" })).toBeDisabled();
  });

  it("shows an office's page with its team and a link to its errors", async () => {
    fakeApi({
      "GET /api/admin/me": () => ({ body: ME }),
      "GET /api/admin/offices/alinea": () => ({
        body: {
          ...ALINEA,
          team: [
            { name: "Ana", email: "dona@alinea.example", role: "owner", status: "active", last_seen_at: "2026-10-25T18:00:00Z" },
            { name: "Bia", email: "bia@alinea.example", role: "member", status: "invited", last_seen_at: null },
          ],
        },
      }),
    });
    renderAt("/escritorios/alinea");
    expect(await screen.findByRole("heading", { name: "Alinea", level: 1 })).toBeInTheDocument();
    const team = screen.getByRole("table");
    expect(within(team).getByText("Bia").closest("tr")).toHaveTextContent("Convite pendente");
    expect(screen.getByRole("link", { name: /Abrir os erros deste escritório/ })).toHaveAttribute(
      "href",
      officeErrorsUrl({ project: "arq-proj", service: "portal" }, ALINEA),
    );
    expect(screen.getByRole("link", { name: "alineaarquitetos.com" })).toHaveAttribute("href", "https://alineaarquitetos.com/painel/");
  });

  it("signs out with the session's CSRF token", async () => {
    const sent = fakeApi({
      "GET /api/admin/me": () => ({ body: ME }),
      "GET /api/admin/offices": () => ({ body: [] }),
      "POST /api/admin/signout": () => ({ status: 204 }),
    });
    renderAt("/");
    await userEvent.click(await screen.findByRole("button", { name: "Sair" }));
    expect(await screen.findByRole("button", { name: "Entrar com Google" })).toBeInTheDocument();
    expect(sent.find((r) => r.path === "/api/admin/signout")?.headers.get("X-CSRF-Token")).toBe("csrf-9");
  });
});

describe("the log links", () => {
  it("search this service's logs for a request, or an office's errors", () => {
    const target = { project: "arq-proj", service: "portal" };
    const support = decodeURIComponent(supportCodeUrl(target, " ABC123 "));
    expect(support).toContain('resource.labels.service_name="portal"');
    expect(support).toContain('("abc123" OR trace="projects/arq-proj/traces/abc123")');
    expect(supportCodeUrl(target, "x")).toContain("?project=arq-proj");
    const errors = decodeURIComponent(officeErrorsUrl(target, { slug: "alinea", id: "u-1" }));
    // By slug or by ID: uploads and emails log the office's ID (Codex, PR #138).
    expect(errors).toContain('severity>=ERROR\n("alinea" OR "u-1")');
  });
});

describe("counts", () => {
  it("say none as zero, though Portuguese reads 0 as singular", async () => {
    fakeApi({
      "GET /api/admin/me": () => ({ body: ME }),
      "GET /api/admin/offices": () => ({
        body: [{ ...ALINEA, staff: 0, owners: 0, downloads: 0, projects: { active: 0, completed: 0, archived: 0, draft: 0 } }],
      }),
    });
    renderAt("/");
    const row = (await screen.findByRole("link", { name: "Alinea" })).closest("tr")!;
    expect(row).toHaveTextContent("0 pessoa");
    expect(row).toHaveTextContent("0 em andamento");
    expect(row).toHaveTextContent("0 download");
    expect(row).not.toHaveTextContent("1 pessoa");
  });
});

describe("usage additions", () => {
  it("loads file statistics only on request and sends the operator CSRF token", async () => {
    const sent = fakeApi({
      "GET /api/admin/me": () => ({ body: ME }),
      "GET /api/admin/offices/alinea": () => ({ body: { ...ALINEA, usage: { descriptions: 3, details: 8 }, link_statuses: { active: 1, expired: 1, disabled: 1 } } }),
      "POST /api/admin/offices/alinea/file-statistics": () => ({ body: { loaded_at: "2026-10-26T12:00:00Z", projects: 7, projects_with_files: 3, files: 4, known_bytes: 1024, unknown_sizes: 1, account_used: null, account_limit: null, types: [{ kind: "pdf", files: 3, known_bytes: 1024, unknown_sizes: 0 }, { kind: "google", files: 1, known_bytes: 0, unknown_sizes: 1 }] } }),
    });
    renderAt("/escritorios/alinea");
    const load = await screen.findByRole("button", { name: "Carregar estatísticas de arquivos" });
    expect(sent.some(r => r.path.endsWith("file-statistics"))).toBe(false);
    expect(screen.getByText("1 ativos · 1 expirados · 1 desativados")).toBeInTheDocument();
    await userEvent.click(load);
    expect(await screen.findByText("PDF")).toBeInTheDocument();
    expect(screen.getByText("3 de 7")).toBeInTheDocument(); // projects with files
    expect(sent.find(r => r.path.endsWith("file-statistics"))?.headers.get("X-CSRF-Token")).toBe("csrf-9");
    const url = new URL(screen.getByRole("link", { name: "Ver este escritório no PostHog" }).getAttribute("href")!);
    expect(JSON.parse(url.searchParams.get("properties")!)).toEqual([{ key: "tenant", value: ["alinea"], operator: "exact", type: "event" }]);
  });

  it("requires the exact name before deleting a suspended office", async () => {
    const sent = fakeApi({
      "GET /api/admin/me": () => ({ body: { ...ME, actions_enabled: true } }),
      "GET /api/admin/offices/alinea": () => ({ body: { ...ALINEA, status: "suspended" } }),
      "GET /api/admin/offices": () => ({ body: [] }),
      "POST /api/admin/offices/alinea/actions": () => ({ body: { owner_url: null } }),
    });
    renderAt("/escritorios/alinea");
    await userEvent.click(await screen.findByRole("button", { name: "Excluir escritório" }));
    const confirm = screen.getByRole("button", { name: "Confirmar" });
    expect(confirm).toBeDisabled();
    const name = screen.getByLabelText("Digite o nome exato do escritório");
    await userEvent.type(name, "alinea");
    expect(confirm).toBeDisabled();
    await userEvent.clear(name);
    await userEvent.type(name, "Alinea");
    await userEvent.click(confirm);
    await vi.waitFor(() => expect(sent.some(r => r.path.endsWith("/actions"))).toBe(true));
    expect(sent.find(r => r.path.endsWith("/actions"))?.headers.get("X-CSRF-Token")).toBe("csrf-9");
  });
});

describe("creating an office", () => {
  it("suggests the identifier from the address until it is edited", () => {
    expect(slugFromHost("alinea.myunio.app")).toBe("alinea");
    expect(slugFromHost(" https://Casa-Norte.myunio.app/painel ")).toBe("casa-norte");
    expect(slugFromHost("-x_y-.example.com")).toBe("xy");
    expect(slugFromHost("")).toBe("");
    expect(hostOf("HTTPS://Alinea.MyUnio.app/")).toBe("alinea.myunio.app");
  });

  it("creates in a dialog and shows the owner's link to copy", async () => {
    const sent = fakeApi({
      "GET /api/admin/me": () => ({ body: { ...ME, actions_enabled: true } }),
      "GET /api/admin/offices": () => ({ body: [] }),
      "POST /api/admin/offices": () => ({ body: { owner_url: "https://horizonte.myunio.app/painel/entrar-na-equipe#token=abc" } }),
    });
    renderAt("/");
    await userEvent.click(await screen.findByRole("button", { name: "Criar escritório" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText("Nome do escritório"), "Ateliê Horizonte");
    await userEvent.type(within(dialog).getByLabelText("Endereço"), "https://Horizonte.myunio.app");
    const slug = within(dialog).getByLabelText("Identificador");
    expect(slug).toHaveValue("horizonte");
    await userEvent.clear(slug);
    await userEvent.type(slug, "horizonte-sp");
    await userEvent.type(within(dialog).getByLabelText("Endereço"), "x"); // no longer follows the address
    expect(slug).toHaveValue("horizonte-sp");
    await userEvent.click(within(dialog).getByRole("button", { name: "Criar e gerar convite do responsável" }));
    expect(await within(dialog).findByLabelText("Link de cadastro do responsável")).toHaveValue("https://horizonte.myunio.app/painel/entrar-na-equipe#token=abc");
    expect(sent.find((r) => r.path === "/api/admin/offices" && r.method === "POST")?.body).toEqual({ name: "Ateliê Horizonte", slug: "horizonte-sp", hostname: "horizonte.myunio.appx" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Concluir" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
