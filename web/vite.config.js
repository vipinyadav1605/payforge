import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The browser only talks to this dev server; /api/* is proxied to the PayForge API.
// Same-origin => no CORS setup needed, and response headers (Idempotent-Replayed) stay readable.
const target = process.env.VITE_API_TARGET || "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/api": { target, changeOrigin: true, rewrite: (p) => p.replace(/^\/api/, "") },
    },
  },
});
