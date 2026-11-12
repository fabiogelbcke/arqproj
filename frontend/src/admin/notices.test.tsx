import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { describe, expect, it } from "vitest";

import { fakeApi } from "../test/render";
import { adminRoutes } from "./AdminApp";
import type { Catalog, Notices } from "./siteSettings";

const ME = { email: "fabio@unio.example", csrf_token: "csrf-9", logs_project: null, logs_service: null, actions_enabled: true };
const CATALOG: Catalog = { can_change: true, limits: {}, types: [], stages: [] };

const NOTICES: Notices = {
  quiet_minutes: 45,
  hold_minutes: 120,
  reminder_morning: "08:30",
  reminder_evening: "18:00",
  reminder_before_minutes: 30,
  ask_again_days: 3,
  whatsapp_news: ["files", "stages", "project", "meetings", "reminders"],
  can_change: true,
  limits: { quietMinutes: [5, 120], holdMinutes: [5, 720], reminderBeforeMinutes: [5, 180], askAgainDays: [1, 30] },
};

function renderNotices(notices: Notices = NOTICES, handlers: Parameters<typeof fakeApi>[0] = {}) {
  const sent = fakeApi({
    "GET /api/admin/me": () => ({ body: ME }),
    "GET /api/admin/settings/types-and-stages": () => ({ body: CATALOG }),
    "GET /api/admin/settings/notices": () => ({ body: notices }),
    ...handlers,
  });
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <RouterProvider router={createMemoryRouter(adminRoutes, { initialEntries: ["/configuracoes/avisos"] })} />
    </QueryClientProvider>,
  );
  return sent;
}

describe("Configurações → Avisos (A48)", () => {
  it("shows the values with their limits, and says they reach every office", async () => {
    renderNotices();
    expect(await screen.findByLabelText(/Tempo sem novidades/)).toHaveValue(45);
    expect(screen.getByLabelText(/Lembrete no dia/)).toHaveValue("08:30");
    expect(screen.getByText(/Entre 5 e 120\./)).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Lembretes de reunião" })).toBeChecked();
    expect(screen.getByRole("note")).toHaveTextContent(/todos os escritórios.*10 minutos/);
  });

  it("saves the changed values, numbers as numbers", async () => {
    const sent = renderNotices(NOTICES, { "PUT /api/admin/settings/notices": () => ({ body: NOTICES }) });
    const quiet = await screen.findByLabelText(/Tempo sem novidades/);
    await userEvent.clear(quiet);
    await userEvent.type(quiet, "30");
    await userEvent.click(screen.getByRole("checkbox", { name: "Arquivos novos" }));
    await userEvent.click(screen.getByRole("button", { name: "Salvar alterações" }));
    await waitFor(() =>
      expect(sent.find((r) => r.method === "PUT")?.body).toMatchObject({
        quiet_minutes: 30,
        hold_minutes: 120,
        reminder_morning: "08:30",
        whatsapp_news: ["stages", "project", "meetings", "reminders"],
      }),
    );
    expect(await screen.findByText("Alterações salvas.")).toBeInTheDocument();
  });

  it("can't be saved with a number left blank", async () => {
    renderNotices();
    await userEvent.clear(await screen.findByLabelText(/Espera máxima/));
    expect(screen.getByRole("button", { name: "Salvar alterações" })).toBeDisabled();
  });

  it("shows the server's refusal in its own words", async () => {
    renderNotices(NOTICES, {
      "PUT /api/admin/settings/notices": () => ({ status: 422, body: { error: "invalid_notice_settings" } }),
    });
    await userEvent.click(await screen.findByRole("button", { name: "Salvar alterações" }));
    expect(await screen.findByText(/a espera máxima não pode ser menor/)).toBeInTheDocument();
  });

  it("only shows the values where the operator login isn't set up", async () => {
    renderNotices({ ...NOTICES, can_change: false });
    expect(await screen.findByLabelText(/Tempo sem novidades/)).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Salvar alterações" })).not.toBeInTheDocument();
  });
});
