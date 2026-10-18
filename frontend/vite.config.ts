/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

// The staff app is served by the Python backend at /painel (backend/web/painel.py),
// the client page at /{slug} (backend/web/pages.py); both built from here.
// In development, Vite serves it instead and forwards /api to the backend, keeping
// the browser's Host header so the backend picks the right office and the
// sign-in cookie belongs to the address in the address bar.
// The deployed app answers on /painel and /painel/ alike; Vite's dev server only
// knows /painel/, so send the bare addresses there.
const devRedirects: Plugin = {
  name: "painel-dev-redirects",
  configureServer(server) {
    server.middlewares.use((request, response, next) => {
      const [path, query] = (request.url ?? "").split("?");
      if (path === "/" || path === "/painel") {
        response.statusCode = 302;
        response.setHeader("Location", "/painel/" + (query ? `?${query}` : ""));
        response.end();
        return;
      }
      // A client page address (`/casa-jardim`): the client page's entry. Deployed,
      // the backend serves it with the preview tags (backend/web/pages.py).
      if (/^\/[a-z0-9-]+$/.test(path ?? "") && path !== "/api") {
        request.url = "/painel/client.html" + (query ? `?${query}` : "");
      }
      next();
    });
  },
};

export default defineConfig({
  base: "/painel/",
  plugins: [react(), devRedirects],
  define: {
    // Compared with the API's X-Build-Id to notice a new deploy (plan A30).
    __BUILD_ID__: JSON.stringify(process.env.BUILD_ID ?? "dev"),
  },
  server: {
    port: 5173,
    strictPort: true,
    allowedHosts: [".localhost"],
    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: false } },
    // The translation catalogs live in backend/i18n, shared with the server.
    fs: { allow: [".", "../backend/i18n"] },
  },
  // Never inline files as data: URLs: the Content Security Policy allows fonts and
  // images only from this site (backend/web/painel.py).
  build: {
    outDir: "dist",
    assetsDir: "assets",
    assetsInlineLimit: 0,
    // Two apps: the painel (index.html) and the client page (client.html), each
    // with only its own code.
    rollupOptions: { input: { painel: "index.html", client: "client.html" } },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
