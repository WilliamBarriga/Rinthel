import { describe, expect, it } from "vitest";
import { DEFAULT_VAD } from "../voice/vad";
import { fetchVoiceSpeech } from "./adapters/fetch-voice-speech";
import { fakeVoiceSpeech, silentPcm } from "./fakes/voice-speech";
import { PortError } from "./http-errors";
import type { VoiceSpeech } from "./voice-speech";

/** A tiny stand-in for the Node routes, with its own state (not the fake). */
function voiceServer({ enabled = true, sessions = ["s1"], tts = true }: { enabled?: boolean; sessions?: string[]; tts?: boolean } = {}) {
  let stored = { enabled, language: "es", vad: { ...DEFAULT_VAD } };
  const refuse = (error: string) => Response.json({ error }, { status: 400 });
  return async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = String(input);
    if (init?.signal?.aborted) throw init.signal.reason;
    if (url === "/api/voice" && (init?.method ?? "GET") === "GET") return Response.json({ ...stored, stt: true, tts, statusSpeech: true, comparison: false, ttsPrefetch: false, sentenceChunks: false, pipelineMode: "parallel" });
    if (url === "/api/voice" && init?.method === "PUT") {
      const body = JSON.parse(String(init.body)) as { enabled: unknown; language?: string; vad?: Partial<typeof DEFAULT_VAD> };
      if (typeof body.enabled !== "boolean") return refuse("enabled debe ser true o false");
      const vad = { ...DEFAULT_VAD, ...body.vad };
      if (!["auto", "en", "es"].includes(body.language ?? "auto")) return refuse("Elige un idioma de entrada admitido");
      if (vad.redemptionMs < 200 || vad.redemptionMs > 3000) return refuse("Valor de detección redemptionMs fuera de rango");
      if (vad.negativeSpeechThreshold >= vad.positiveSpeechThreshold) return refuse("El umbral de fin de voz debe ser menor que el de inicio");
      stored = { enabled: body.enabled, language: body.language ?? "auto", vad };
      return Response.json(stored);
    }
    const route = /^\/api\/sessions\/([^/]+)\/voice\/(speech|transcribe)$/.exec(url);
    if (!route) return Response.json({ error: "No such route" }, { status: 404 });
    if (!sessions.includes(decodeURIComponent(route[1]))) return Response.json({ error: "La voz solo está disponible en tus propias Sesiones." }, { status: 403 });
    if (!stored.enabled) return Response.json({ error: "Activa la voz en Voz antes de usarla." }, { status: 409 });
    if (route[2] === "speech") {
      if (!tts) return Response.json({ error: "La Instance no tiene un Local model de tts activo" }, { status: 409 });
      const { text } = JSON.parse(String(init?.body)) as { text: string };
      if (text.length < 1 || text.length > 600) return Response.json({ error: "El texto a decir debe tener entre 1 y 600 caracteres" }, { status: 400 });
      return new Response(silentPcm(text) as BodyInit, { headers: { "Content-Type": "audio/pcm", "X-Sample-Rate": "24000", "X-Voice-Streaming": "true" } });
    }
    if (((init?.body as Blob | undefined)?.size ?? 0) === 0) return Response.json({ error: "Hace falta una grabación WAV" }, { status: 400 });
    return Response.json({ text: "hello" });
  };
}

const live = () => new AbortController().signal;
const wav = new Blob([new Uint8Array([1, 2, 3, 4])], { type: "audio/wav" });

async function bytesOf(body: ReadableStream<Uint8Array> | null): Promise<number> {
  let total = 0;
  const reader = body!.getReader();
  for (let r = await reader.read(); !r.done; r = await reader.read()) total += r.value.length;
  return total;
}

/** Same suite for every adapter of the port; it only uses the interface. */
function voiceSpeechContract(name: string, make: (options?: { enabled?: boolean; tts?: boolean }) => VoiceSpeech) {
  describe(`VoiceSpeech (${name})`, () => {
    it("settings dice si la voz del lector está activada y si la Instance tiene stt y tts", async () => {
      expect(await make().settings()).toMatchObject({ enabled: true, stt: true, tts: true });
      expect(await make({ enabled: false, tts: false }).settings()).toMatchObject({ enabled: false, tts: false });
    });

    it("settings trae la detección por omisión; saveConfig guarda y devuelve lo guardado, y settings lo lee de vuelta", async () => {
      const voice = make({ enabled: false });
      expect((await voice.settings()).vad).toEqual(DEFAULT_VAD);
      const saved = await voice.saveConfig({ enabled: true, language: "es", vad: { ...DEFAULT_VAD, redemptionMs: 1500 } });
      expect(saved).toMatchObject({ enabled: true, language: "es", vad: { redemptionMs: 1500 } });
      expect(await voice.settings()).toMatchObject({ enabled: true, language: "es" });
    });

    it("saveConfig rechaza con 400 un idioma no admitido, una detección fuera de rango o un fin de voz no menor que el inicio, sin guardar nada", async () => {
      const voice = make({ enabled: false });
      await expect(voice.saveConfig({ enabled: true, language: "xx" })).rejects.toMatchObject({ kind: "http", status: 400 });
      await expect(voice.saveConfig({ enabled: true, vad: { ...DEFAULT_VAD, redemptionMs: 10 } })).rejects.toMatchObject({ status: 400 });
      await expect(voice.saveConfig({ enabled: true, vad: { ...DEFAULT_VAD, negativeSpeechThreshold: 0.7 } })).rejects.toMatchObject({ status: 400 });
      expect((await voice.settings()).enabled).toBe(false);
    });

    it("speak devuelve PCM de 24 kHz que se lee entero, más largo cuanto más largo el texto", async () => {
      const voice = make();
      const short = await voice.speak("s1", "hola", live());
      expect([short.format, short.streaming]).toEqual(["pcm", true]);
      const shortBytes = await bytesOf(short.body);
      expect(shortBytes).toBeGreaterThan(0);
      expect(await bytesOf((await voice.speak("s1", "hola, qué tal", live())).body)).toBeGreaterThan(shortBytes);
    });

    it("transcribe devuelve el texto reconocido", async () => {
      expect((await make().transcribe("s1", wav, live())).text).toBe("hello");
    });

    it("un texto fuera de 1 a 600 caracteres y una grabación vacía son 400 con el mensaje del servidor", async () => {
      const voice = make();
      for (const text of ["", "x".repeat(601)]) {
        await expect(voice.speak("s1", text, live())).rejects.toMatchObject({ name: "PortError", status: 400, message: "El texto a decir debe tener entre 1 y 600 caracteres" });
      }
      await expect(voice.transcribe("s1", new Blob([]), live())).rejects.toMatchObject({ status: 400 });
    });

    it("la voz apagada o sin tts es 409; la Sesión de otro es 403", async () => {
      const off = make({ enabled: false });
      await expect(off.speak("s1", "hola", live())).rejects.toMatchObject({ status: 409 });
      await expect(off.transcribe("s1", wav, live())).rejects.toMatchObject({ status: 409 });
      await expect(make({ tts: false }).speak("s1", "hola", live())).rejects.toMatchObject({ status: 409 });
      await expect(make().speak("ajena", "hola", live())).rejects.toMatchObject({ status: 403 });
    });

    it("una señal abortada rechaza con su razón, no con un PortError", async () => {
      const controller = new AbortController();
      const reason = new Error("barge-in");
      controller.abort(reason);
      await expect(make().speak("s1", "hola", controller.signal)).rejects.toBe(reason);
      await expect(make().transcribe("s1", wav, controller.signal)).rejects.toBe(reason);
      expect(reason).not.toBeInstanceOf(PortError);
    });
  });
}

voiceSpeechContract("fake", ({ enabled = true, tts = true } = {}) => fakeVoiceSpeech({ config: { enabled, language: "es" }, tts }));
voiceSpeechContract("fetch", (options) => fetchVoiceSpeech(voiceServer(options)));

describe("fetchVoiceSpeech", () => {
  it("saveConfig va a /api/voice con PUT y el cuerpo tal cual", async () => {
    const calls: Array<[string, string | undefined, unknown]> = [];
    const api = fetchVoiceSpeech(async (input, init) => {
      calls.push([String(input), init?.method, JSON.parse(String(init?.body))]);
      return Response.json({ enabled: true });
    });
    await api.saveConfig({ enabled: true });
    expect(calls).toEqual([["/api/voice", "PUT", { enabled: true }]]);
  });

  it("un 401 y un 502 se distinguen del resto, como en los demás adaptadores", async () => {
    const down = (status: number) => fetchVoiceSpeech(async () => Response.json({ error: "x" }, { status }));
    await expect(down(401).speak("s1", "hola", live())).rejects.toMatchObject({ kind: "unauthorized" });
    await expect(down(502).transcribe("s1", wav, live())).rejects.toMatchObject({ kind: "unavailable" });
  });

  it("un corte de red es un PortError de red", async () => {
    const cut = fetchVoiceSpeech(async () => { throw new TypeError("offline"); });
    await expect(cut.speak("s1", "hola", live())).rejects.toMatchObject({ kind: "network", message: "offline" });
  });

  it("un audio que no es PCM de 24 kHz se rechaza y uno codificado se entrega como encoded", async () => {
    const wrong = fetchVoiceSpeech(async () => new Response(new Uint8Array(4), { headers: { "Content-Type": "audio/pcm", "X-Sample-Rate": "16000" } }));
    await expect(wrong.speak("s1", "hola", live())).rejects.toMatchObject({ message: "Audio de voz no admitido" });
    const mp3 = fetchVoiceSpeech(async () => new Response(new Uint8Array(4), { headers: { "Content-Type": "audio/mpeg" } }));
    expect(await mp3.speak("s1", "hola", live())).toMatchObject({ format: "encoded", streaming: false });
  });
});
