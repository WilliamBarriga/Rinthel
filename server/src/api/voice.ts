import express, { type Router } from "express";

/**
 * Voice in and out: proxies to the two local CPU-only services orchestrated
 * by Rinthel-general (whisper.cpp for STT, a Piper wrapper for TTS). Both are
 * loopback-only, same trust model as LLAMA_BASE_URL — no auth between this
 * server and them, only between the browser and this server.
 */
const WHISPER_BASE_URL = process.env.WHISPER_BASE_URL || "http://127.0.0.1:8090";
const TTS_BASE_URL = process.env.TTS_BASE_URL || "http://127.0.0.1:8091";

export function voiceRouter(): Router {
  const router = express.Router();

  // Scoped to this route only, and only for audio/* — the global
  // express.json() 2mb limit (index.ts) stays untouched for every other
  // route, and a browser recording needs more headroom than that anyway.
  router.post(
    "/voice/transcribe",
    express.raw({ type: "audio/*", limit: "25mb" }),
    async (req, res) => {
      if (!Buffer.isBuffer(req.body) || req.body.length === 0) {
        return res.status(400).json({ error: "Expected an audio body" });
      }

      const form = new FormData();
      const contentType = req.headers["content-type"] || "audio/webm";
      form.append("file", new Blob([new Uint8Array(req.body)], { type: contentType }), "audio");
      // verbose_json is the only format that reports detected_language — needed
      // so the TTS reply comes back in the language the user actually spoke.
      form.append("response_format", "verbose_json");

      try {
        const upstream = await fetch(`${WHISPER_BASE_URL}/inference`, {
          method: "POST",
          body: form,
        });
        if (!upstream.ok) {
          return res.status(502).json({ error: `whisper.cpp returned ${upstream.status}` });
        }
        const data = (await upstream.json()) as { text?: string; detected_language?: string };
        // whisper.cpp reports the full language name ("spanish", "english"),
        // not an ISO code. Only es/en are wired to a Piper voice (Fase 2).
        const lang = (data.detected_language || "").toLowerCase().includes("span") ? "es" : "en";
        res.json({ text: (data.text ?? "").trim(), lang });
      } catch (err) {
        res.status(502).json({ error: `whisper.cpp unreachable: ${(err as Error).message}` });
      }
    }
  );

  // The global express.json() already parses this body — no multipart here.
  router.post("/voice/speak", async (req, res) => {
    const { text, lang } = req.body ?? {};
    if (typeof text !== "string" || !text.trim()) {
      return res.status(400).json({ error: "text is required" });
    }

    try {
      const upstream = await fetch(`${TTS_BASE_URL}/speak`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, lang: typeof lang === "string" ? lang : "es" }),
      });
      if (!upstream.ok) {
        return res.status(502).json({ error: `TTS engine returned ${upstream.status}` });
      }
      const audio = Buffer.from(await upstream.arrayBuffer());
      res.setHeader("Content-Type", upstream.headers.get("content-type") || "audio/wav");
      res.send(audio);
    } catch (err) {
      res.status(502).json({ error: `TTS engine unreachable: ${(err as Error).message}` });
    }
  });

  return router;
}
