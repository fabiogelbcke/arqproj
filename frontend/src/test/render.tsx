import { QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { vi } from "vitest";

import { makeQueryClient } from "../app/App";
import { routes } from "../app/routes";

type Reply = { status?: number; body?: unknown; headers?: Record<string, string> };
type Handler = (body: unknown) => Reply | Promise<Reply>;

/** Fake API: handlers keyed by "METHOD /path"; records what the app sent. */
export function fakeApi(handlers: Record<string, Handler>) {
  const sent: { method: string; path: string; query: string; body: unknown; headers: Headers }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (given: Request | string) => {
      const input = typeof given === "string" ? new Request(new URL(given, window.location.origin)) : given;
      const { pathname: path, search: query } = new URL(input.url);
      const body = input.method === "GET" ? undefined : await input.clone().json().catch(() => undefined);
      sent.push({ method: input.method, path, query, body, headers: input.headers });
      const handler = handlers[`${input.method} ${path}`];
      const answer = handler ? handler(body) : { status: 404, body: { error: "not_found" } };
      // Only a handler that answers later is waited for: other replies keep their timing.
      const reply = answer instanceof Promise ? await answer : answer;
      return new Response(reply.status === 204 ? null : JSON.stringify(reply.body ?? {}), {
        status: reply.status ?? 200,
        headers: { "Content-Type": "application/json", ...reply.headers },
      });
    }),
  );
  return sent;
}

export const TENANT = { name: "Alinea", slug: "alinea", locale: "pt-BR", analytics: null };
export const ME = {
  email: "ana@alinea.example",
  name: "Ana",
  role: "owner",
  tenant_slug: "alinea",
  tenant_name: "Alinea",
  tenant_locale: "pt-BR",
  tenant_timezone: "America/Sao_Paulo",
  csrf_token: "csrf-123",
  email_confirmed: true,
};
export const notSignedIn: Reply = { status: 401, body: { error: "not_signed_in" } };

export function renderAt(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(
    <QueryClientProvider client={makeQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}
