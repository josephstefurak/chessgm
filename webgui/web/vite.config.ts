import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Where `python gui.py` listens. Only `npm run dev` uses this.
const SERVER = "http://127.0.0.1:8765";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
    target: "es2022",
    // Never inline assets as data: URIs. The server's content security policy
    // only allows fonts from its own origin.
    assetsInlineLimit: 0,
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      // The game server refuses any Host or Origin but its own, so the dev proxy
      // presents itself as that server. This exists only on the developer's machine.
      "/api": { target: SERVER, changeOrigin: true, headers: { origin: SERVER } },
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
