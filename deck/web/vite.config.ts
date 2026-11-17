import { createReadStream } from "node:fs";
import { resolve } from "node:path";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

/** Voice detection's model and runtime (`scripts/copy-vad-assets.mjs`), the only files under `/voice-assets/`. */
const VOICE_ASSETS = new Set(["ort-wasm-simd-threaded.mjs", "ort-wasm-simd-threaded.wasm", "silero_vad_v5.onnx", "vad.worklet.bundle.min.js"]);

export default defineConfig({
  plugins: [react(), {
    name: "voice-assets",
    configureServer(server) {
      // ONNX Runtime imports its runtime at run time: in development these are served as plain
      // static files, as the built app serves them, and never transformed by Vite.
      server.middlewares.use((req, res, next) => {
        const path = new URL(req.url || "/", "http://localhost").pathname;
        const name = path.slice("/voice-assets/".length);
        if (!path.startsWith("/voice-assets/") || !VOICE_ASSETS.has(name)) return next();
        res.setHeader("Content-Type", name.endsWith("wasm") ? "application/wasm" : name.endsWith("onnx") ? "application/octet-stream" : "text/javascript");
        const file = createReadStream(resolve(server.config.publicDir, "voice-assets", name));
        file.on("error", () => { res.statusCode = 404; res.end(); });
        file.pipe(res);
      });
    },
  }],
  test: { environment: "jsdom", include: ["src/**/*.test.{ts,tsx}"] },
  server: { port: 5190, proxy: { "/api": process.env.DECK_API_URL || "http://localhost:4100" } },
});
