import type { VoiceConfig, VoiceSettings } from "@deck/contract";
import { DEFAULT_VAD, VOICE_LANGUAGES } from "../../voice/vad";
import { PortError } from "../http-errors";
import type { SpeechAudio, Transcription, VoiceSpeech } from "../voice-speech";

export interface FakeVoiceSpeech extends VoiceSpeech {
  /** Makes the next call to `op` (a method name of the port) reject with `error`. */
  failNext(op: keyof VoiceSpeech, error: Error): void;
  /** What the next `transcribe` recognises (queued, in order); after them it answers `fallback`. */
  heard(...texts: string[]): void;
  /** Turns a Capability of the Instance on or off, as the admin would. */
  setCapability(capability: "stt" | "tts", on: boolean): void;
  /** Every config `saveConfig` accepted, in order (a refused one is not here). */
  readonly configSaved: Required<VoiceConfig>[];
  /** Every phrase `speak` was asked, in order. */
  readonly spoken: { sessionId: string; text: string }[];
  /** Size in bytes of every recording `transcribe` got, in order. */
  readonly recorded: { sessionId: string; bytes: number }[];
}

const VAD_RANGES = [["positiveSpeechThreshold", 0.01, 1], ["negativeSpeechThreshold", 0, 0.99], ["minSpeechMs", 64, 2000], ["preSpeechPadMs", 0, 1000], ["redemptionMs", 200, 3000]] as const;

export const FAKE_SAMPLE_RATE = 24000;
/** Audio of the fake speech: 10 ms of silence per character, so a longer phrase lasts longer. */
const SAMPLES_PER_CHAR = FAKE_SAMPLE_RATE / 100;

export function silentPcm(text: string): Uint8Array {
  return new Uint8Array(text.length * SAMPLES_PER_CHAR * 2);
}

/**
 * Voice that needs nothing: `speak` answers silent PCM of a length that follows the text, and
 * `transcribe` answers what `heard` queued. It refuses like the server does: a text outside 1 to 600
 * characters or an empty recording is `400`, a Session not in `sessions` (someone else's) is `403`,
 * and voice off or a Capability off is `409`.
 */
export function fakeVoiceSpeech({ config = {}, sessions = ["s1"], fallback = "hello", stt = true, tts = true }: { config?: Partial<VoiceConfig>; sessions?: string[]; fallback?: string; stt?: boolean; tts?: boolean } = {}): FakeVoiceSpeech {
  let settings: Required<VoiceConfig> = { enabled: true, language: "auto", ...config, vad: { ...DEFAULT_VAD, ...config.vad } };
  const on = { stt, tts };
  const configSaved: Required<VoiceConfig>[] = [];
  const failures = new Map<keyof VoiceSpeech, Error>();
  const queue: string[] = [];
  const spoken: FakeVoiceSpeech["spoken"] = [];
  const recorded: FakeVoiceSpeech["recorded"] = [];
  const check = (op: keyof VoiceSpeech, sessionId?: string, capability?: "stt" | "tts") => {
    const error = failures.get(op);
    if (error) {
      failures.delete(op);
      throw error;
    }
    if (sessionId === undefined) return;
    if (!sessions.includes(sessionId)) throw new PortError("http", 403, "La voz solo está disponible en tus propias Sesiones.");
    if (!settings.enabled) throw new PortError("http", 409, "Activa la voz en Voz antes de usarla.");
    if (capability && !on[capability]) throw new PortError("http", 409, `La Instance no tiene un Local model de ${capability} activo: un admin puede activarlo.`);
  };
  return {
    spoken,
    recorded,
    configSaved,
    async settings() {
      check("settings");
      return { ...structuredClone(settings), ...on, statusSpeech: true, comparison: false, ttsPrefetch: false, sentenceChunks: false, pipelineMode: "parallel" };
    },
    async saveConfig(next) {
      check("saveConfig");
      if (typeof next.enabled !== "boolean") throw new PortError("http", 400, "enabled debe ser true o false");
      const language = next.language ?? "auto";
      if (!VOICE_LANGUAGES.some(([code]) => code === language)) throw new PortError("http", 400, "Elige un idioma de entrada admitido");
      const vad = { ...DEFAULT_VAD, ...next.vad };
      for (const [key, min, max] of VAD_RANGES) {
        if (typeof vad[key] !== "number" || !Number.isFinite(vad[key]) || vad[key] < min || vad[key] > max) throw new PortError("http", 400, `Valor de detección ${key} fuera de rango: ${min}–${max}`);
      }
      if (vad.negativeSpeechThreshold >= vad.positiveSpeechThreshold) throw new PortError("http", 400, "El umbral de fin de voz debe ser menor que el de inicio");
      settings = { vad, language, enabled: next.enabled };
      configSaved.push(structuredClone(settings));
      return structuredClone(settings);
    },
    async speak(sessionId, text, signal): Promise<SpeechAudio> {
      signal.throwIfAborted();
      check("speak", sessionId, "tts");
      if (text.length < 1 || text.length > 600) throw new PortError("http", 400, "El texto a decir debe tener entre 1 y 600 caracteres");
      spoken.push({ sessionId, text });
      const bytes = silentPcm(text);
      const body = new ReadableStream<Uint8Array>({ start(controller) { controller.enqueue(bytes); controller.close(); } });
      return { format: "pcm", streaming: true, body, serverTiming: "" };
    },
    async transcribe(sessionId, wav, signal): Promise<Transcription> {
      signal.throwIfAborted();
      check("transcribe", sessionId, "stt");
      if (wav.size === 0) throw new PortError("http", 400, "Hace falta una grabación WAV");
      recorded.push({ sessionId, bytes: wav.size });
      return { text: queue.shift() ?? fallback, serverTiming: "" };
    },
    heard: (...texts) => void queue.push(...texts),
    setCapability: (capability, value) => { on[capability] = value; },
    failNext: (op, error) => void failures.set(op, error),
  };
}
