import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Relative asset paths + hash routing: the dashboard works at any URL prefix (e.g. behind a proxy).
export default defineConfig({
  base: "./",
  build: { chunkSizeWarningLimit: 1200 },
  plugins: [react()],
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
});
