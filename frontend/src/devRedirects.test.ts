// The dev server's routing (vite.config.ts) sends each address to the bundle
// the backend would serve deployed.
import { describe, expect, it } from "vitest";

import { devRedirects } from "../vite.config";

type Middleware = (request: { url: string; headers: { host?: string } }, response: unknown, next: () => void) => void;

/** Where the request goes: the bundle it was rewritten to, or "→ <address>" for a redirect. */
function routed(url: string, host: string): string {
  let middleware!: Middleware;
  const configure = devRedirects.configureServer as (server: unknown) => void;
  configure({ middlewares: { use: (handler: Middleware) => (middleware = handler) } });
  const request = { url, headers: { host } };
  let location = "";
  const response = { setHeader: (name: string, value: string) => name === "Location" && (location = value), end: () => {} };
  middleware(request, response, () => {});
  return location ? `→ ${location}` : request.url;
}

describe("the dev server's routing", () => {
  it("serves the office-creation page from the dashboard's bundle on Unio's address", () => {
    expect(routed("/criar-escritorio", "localhost:5173")).toBe("/painel/admin.html");
  });

  it("leaves that path to a project on an office's address", () => {
    expect(routed("/criar-escritorio", "alinea.localhost:5173")).toBe("/painel/client.html");
  });

  it("leaves an office's root and its /brand assets to the backend, where the portfolio is (A44)", () => {
    expect(routed("/", "alinea.localhost:5173")).toBe("/");
    expect(routed("/?previa=1", "alinea.localhost:5173")).toBe("/?previa=1");
    expect(routed("/brand/portfolio.css", "alinea.localhost:5173")).toBe("/brand/portfolio.css");
    // Unio's own address keeps the shortcut to the painel.
    expect(routed("/", "localhost:5173")).toBe("→ /painel/");
    expect(routed("/painel?x=1", "alinea.localhost:5173")).toBe("→ /painel/?x=1");
  });

  it("still serves the dashboard and project pages as before", () => {
    expect(routed("/admin/escritorios/alinea", "localhost:5173")).toBe("/painel/admin.html");
    expect(routed("/casa-jardim", "alinea.localhost:5173")).toBe("/painel/client.html");
  });
});
