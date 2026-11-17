import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: { environment: "jsdom", include: ["src/**/*.test.{ts,tsx}"] },
  server: {
    port: 5190,
    proxy: {
      "/api": process.env.DECK_API_URL || "http://localhost:4100",
      // The Instance browser's view, and its websocket.
      "/browser-ui": { target: process.env.DECK_API_URL || "http://localhost:4100", ws: true },
    },
  },
});
