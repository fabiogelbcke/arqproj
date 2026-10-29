// The dev server's routing (vite.config.ts) sends each address to the bundle
// the backend would serve deployed.
import { describe, expect, it } from "vitest";

import { devRedirects } from "../vite.config";

type Middleware = (request: { url: string; headers: { host?: string } }, response: unknown, next: () => void) => void;

function routed(url: string, host: string): string {
  let middleware!: Middleware;
  const configure = devRedirects.configureServer as (server: unknown) => void;
  configure({ middlewares: { use: (handler: Middleware) => (middleware = handler) } });
  const request = { url, headers: { host } };
  middleware(request, {}, () => {});
  return request.url;
}

describe("the dev server's routing", () => {
  it("serves the office-creation page from the dashboard's bundle on Unio's address", () => {
    expect(routed("/criar-escritorio", "localhost:5173")).toBe("/painel/admin.html");
  });

  it("leaves that path to a project on an office's address", () => {
    expect(routed("/criar-escritorio", "alinea.localhost:5173")).toBe("/painel/client.html");
  });

  it("still serves the dashboard and project pages as before", () => {
    expect(routed("/admin/escritorios/alinea", "localhost:5173")).toBe("/painel/admin.html");
    expect(routed("/casa-jardim", "alinea.localhost:5173")).toBe("/painel/client.html");
  });
});
