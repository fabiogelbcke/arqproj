// The typed API client. Types come from the backend's OpenAPI description
// (`make api-types`), so request and response shapes, roles, languages and error
// codes always match the server.
import createClient, { type Middleware } from "openapi-fetch";

import { noteServerBuild } from "../app/version";
import type { components, paths } from "./schema";

export type Schemas = components["schemas"];
export type ErrorCode = Schemas["ErrorCode"];
export type Me = Schemas["MeOut"];

// The API is on the same origin as the painel (plan A20).
export const api = createClient<paths>({
  baseUrl: window.location.origin,
  // Looked up per request rather than captured once, so tests can stand in for it.
  fetch: (request) => globalThis.fetch(request),
});

// Every state-changing request carries the session's CSRF token (step 1.5).
let csrfToken: string | null = null;
export function setCsrfToken(token: string | null): void {
  csrfToken = token;
}

const middleware: Middleware = {
  onRequest({ request }) {
    if (request.method !== "GET" && csrfToken) request.headers.set("X-CSRF-Token", csrfToken);
    return request;
  },
  onResponse({ response }) {
    noteServerBuild(response.headers.get("X-Build-Id"));
    return response;
  },
};
api.use(middleware);

/** What went wrong, as a code the screens translate, plus the support reference. */
export class ApiError extends Error {
  constructor(
    readonly code: ErrorCode | "unexpected" | "network",
    readonly status?: number,
    readonly requestId?: string | null,
    // Office content that explains the error, e.g. the project that has an address.
    readonly conflictName?: string | null,
  ) {
    super(code);
  }
}

/** The response data, or an ApiError. Never exposes server text (AGENTS.md). */
export async function call<T>(
  request: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  let result;
  try {
    result = await request;
  } catch {
    throw new ApiError("network");
  }
  const { data, error, response } = result;
  if (error !== undefined || !response.ok) {
    const body = error as { error?: unknown; conflict_name?: unknown } | undefined;
    throw new ApiError(
      typeof body?.error === "string" ? (body.error as ErrorCode) : "unexpected",
      response.status,
      response.headers.get("X-Request-ID"),
      typeof body?.conflict_name === "string" ? body.conflict_name : null,
    );
  }
  return data as T;
}
