/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The staff app is served by the Python backend at /painel (backend/web/painel.py).
// In development, Vite serves it instead and forwards /api to the backend, keeping
// the browser's Host header so the backend picks the right office and the
// sign-in cookie belongs to the address in the address bar.
export default defineConfig({
  base: "/painel/",
  plugins: [react()],
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
  build: { outDir: "dist", assetsDir: "assets", assetsInlineLimit: 0 },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
