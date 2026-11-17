import { once } from "node:events";
import express, { type Router } from "express";
import type { VoiceFlags, VoiceSettings } from "@deck/contract";
import type { PortalStore } from "../store/port.js";
import { identityOf } from "../identity.js";
import { SPEECH_SAMPLE_RATE, VoiceSpeechError, type VoiceSpeech } from "../voice/voice-speech.js";
import { VoiceConfigError, voiceConfigs } from "../voice/voice-config.js";

/**
 * Voice, the HTTP side of speech: each user's own settings (`/voice`) and, in a Session of their own,
 * speech-to-text and text-to-speech (`/sessions/:id/voice/*`). The audio is made by the `VoiceSpeech`
 * port; which adapter answers is composed in `index.ts`, not here.
 *
 * Voice is the owner's, in their own Sessions: anyone else (an admin too) is a 403, a Session with no
 * owner as well. With the owner's voice off the routes are a 409, and so is a Capability (`stt`, `tts`)
 * the Instance has no active Local model for.
 */

/** How long one request may take in all, retries included. */
const REQUEST_TIMEOUT_MS = 120000;
const NOT_YOURS = "La voz solo está disponible en tus propias Sesiones.";

export interface VoiceDeps {
  store: Pick<PortalStore, "sessions" | "settings">;
  speech: VoiceSpeech;
  /** The `VOICE_*` switches, read at boot. */
  flags: VoiceFlags;
}

export function pcmWav(pcm: Buffer, sampleRate = SPEECH_SAMPLE_RATE): Buffer {
  if (!pcm.length || pcm.length % 2) throw new Error("El TTS devolvió audio PCM inválido");
  const header = Buffer.alloc(44);
  header.write("RIFF"); header.writeUInt32LE(36 + pcm.length, 4); header.write("WAVEfmt ", 8);
  header.writeUInt32LE(16, 16); header.writeUInt16LE(1, 20); header.writeUInt16LE(1, 22);
  header.writeUInt32LE(sampleRate, 24); header.writeUInt32LE(sampleRate * 2, 28);
  header.writeUInt16LE(2, 32); header.writeUInt16LE(16, 34);
  header.write("data", 36); header.writeUInt32LE(pcm.length, 40);
  return Buffer.concat([header, pcm]);
}

/** Aborted when the browser goes away or the request runs out of time. */
function requestSignal(res: express.Response): { signal: AbortSignal; abort: AbortController } {
  const abort = new AbortController();
  res.on("close", () => abort.abort());
  return { abort, signal: AbortSignal.any([abort.signal, AbortSignal.timeout(REQUEST_TIMEOUT_MS)]) };
}

/** The error as JSON while nothing was sent yet; a cut connection once audio started. */
function failVoice(res: express.Response, e: unknown): void {
  if (res.destroyed) return;
  if (res.headersSent) res.destroy(e as Error);
  else res.status(e instanceof VoiceSpeechError ? e.status : 502).json({ error: (e as Error).message });
}

export function voiceRouter(deps: VoiceDeps): Router {
  const router = express.Router();
  const configs = voiceConfigs(deps.store.settings);
  const reader = (req: express.Request) => identityOf(req)!.userId;

  router.get("/voice", async (req, res) => {
    const settings: VoiceSettings = { ...(await configs.read(reader(req))), ...deps.flags, ...(await deps.speech.available()) };
    res.json(settings);
  });

  router.put("/voice", async (req, res) => {
    try {
      res.json(await configs.save(reader(req), req.body));
    } catch (e) {
      if (e instanceof VoiceConfigError) res.status(400).json({ error: e.message });
      else res.status(500).json({ error: "No se pudo guardar la configuración de voz." });
    }
  });

  router.use("/sessions/:id/voice", async (req, res, next) => {
    const session = await deps.store.sessions.get(String(req.params.id));
    if (!session) return res.status(404).json({ error: "Sesión no encontrada" });
    if (session.owner_user_id === null || session.owner_user_id !== reader(req)) return res.status(403).json({ error: NOT_YOURS });
    const config = await configs.read(reader(req));
    if (!config.enabled) return res.status(409).json({ error: "Activa la voz en Voz antes de usarla." });
    res.locals.language = config.language;
    next();
  });

  router.post("/sessions/:id/voice/transcribe", express.raw({ type: "audio/wav", limit: "12mb" }), async (req, res) => {
    if (!Buffer.isBuffer(req.body) || req.body.length < 44 || req.body.toString("ascii", 0, 4) !== "RIFF")
      return res.status(400).json({ error: "Hace falta una grabación WAV" });
    const { signal } = requestSignal(res);
    try {
      const started = performance.now();
      const text = await deps.speech.transcribe(new Uint8Array(req.body), { language: res.locals.language as string, signal });
      res.set("Server-Timing", `stt_upstream;dur=${(performance.now() - started).toFixed(1)}`);
      res.json({ text });
    } catch (e) { failVoice(res, e); }
  });

  router.post("/sessions/:id/voice/speech", async (req, res) => {
    const started = performance.now();
    const text = req.body?.text;
    if (typeof text !== "string" || !text.trim() || text.length > 600)
      return res.status(400).json({ error: "El texto a decir debe tener entre 1 y 600 caracteres" });
    const { signal, abort } = requestSignal(res);
    try {
      const { sampleRate, pcm } = await deps.speech.speak(text, { signal });
      if (req.get("accept") === "audio/pcm") {
        res.set({ "Content-Type": "audio/pcm", "X-Sample-Rate": String(sampleRate), "X-Sample-Format": "s16le", "Cache-Control": "no-store", "X-Accel-Buffering": "no", "X-Voice-Streaming": "true" });
        res.set("Server-Timing", `tts_headers;dur=${(performance.now() - started).toFixed(1)}`);
        res.flushHeaders();
        const reader = pcm.getReader();
        let bytes = 0;
        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            bytes += value.length;
            if (!res.write(value)) await once(res, "drain", { signal: abort.signal });
          }
          if (!bytes || bytes % 2) throw new Error("El TTS devolvió audio PCM inválido");
          res.end();
        } finally { await reader.cancel().catch(() => {}); reader.releaseLock(); }
        return;
      }
      const wav = pcmWav(Buffer.from(await new Response(pcm).arrayBuffer()), sampleRate);
      res.set({ "Content-Type": "audio/wav", "Cache-Control": "no-store" }).send(wav);
    } catch (e) { failVoice(res, e); }
  });

  return router;
}
