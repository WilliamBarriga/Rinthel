import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: { environment: "jsdom", include: ["src/**/*.test.{ts,tsx}"] },
  server: { port: 5190, proxy: { "/api": process.env.DECK_API_URL || "http://localhost:4200" } },
});
