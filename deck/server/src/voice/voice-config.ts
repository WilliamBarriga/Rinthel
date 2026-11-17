import type { VoiceConfig, VoiceFlags, VoiceVad } from "@deck/contract";
import type { SettingsRepo } from "../store/port.js";

/**
 * Each user's voice settings, on the portal's key/value port (`voice:user:<id>`): whether the voice
 * controls show in their Sessions, the input language and the speech detection. A field never saved
 * reads as its default.
 */

export const DEFAULT_VAD: VoiceVad = { positiveSpeechThreshold: 0.65, negativeSpeechThreshold: 0.35, minSpeechMs: 256, preSpeechPadMs: 320, redemptionMs: 1000 };

/** whisper's codes the settings offer. */
export const VOICE_LANGUAGES = ["auto", "en", "hi", "bn", "ta", "te", "mr", "gu", "kn", "ml", "ur", "zh", "ja", "ko", "es", "fr", "de", "it", "pt", "ar", "ru"] as const;

const VAD_RANGES = [
  ["positiveSpeechThreshold", 0.01, 1], ["negativeSpeechThreshold", 0, 0.99], ["minSpeechMs", 64, 2000], ["preSpeechPadMs", 0, 1000], ["redemptionMs", 200, 3000],
] as const;

/** A setting the user cannot save; its message is for them. */
export class VoiceConfigError extends Error {}

/** The settings as they will be stored, or a `VoiceConfigError`. */
export function validateVoiceConfig(value: any): Required<VoiceConfig> {
  if (typeof value?.enabled !== "boolean") throw new VoiceConfigError("enabled debe ser true o false");
  const language = value.language ?? "auto";
  if (!(VOICE_LANGUAGES as readonly string[]).includes(language)) throw new VoiceConfigError("Elige un idioma de entrada admitido");
  const vad = { ...DEFAULT_VAD, ...value.vad };
  for (const [key, min, max] of VAD_RANGES) {
    if (typeof vad[key] !== "number" || !Number.isFinite(vad[key]) || vad[key] < min || vad[key] > max) throw new VoiceConfigError(`Valor de detección ${key} fuera de rango: ${min}–${max}`);
  }
  if (vad.negativeSpeechThreshold >= vad.positiveSpeechThreshold) throw new VoiceConfigError("El umbral de fin de voz debe ser menor que el de inicio");
  return { enabled: value.enabled, language, vad };
}

const keyOf = (userId: number) => `voice:user:${userId}`;

export function voiceConfigs(settings: SettingsRepo) {
  return {
    async read(userId: number): Promise<Required<VoiceConfig>> {
      const stored = (await settings.all())[keyOf(userId)];
      let saved: any = {};
      try { saved = stored ? JSON.parse(stored) : {}; } catch { /* a damaged value reads as never saved */ }
      return { enabled: saved.enabled === true, language: typeof saved.language === "string" ? saved.language : "auto", vad: { ...DEFAULT_VAD, ...saved.vad } };
    },
    async save(userId: number, value: unknown): Promise<Required<VoiceConfig>> {
      const config = validateVoiceConfig(value);
      await settings.set(keyOf(userId), JSON.stringify(config));
      return config;
    },
  };
}

/** The `VOICE_*` switches of the pipeline the web reads from `GET /api/voice`, read once at boot. */
export function voiceFlagsFromEnv(env: Record<string, string | undefined>): VoiceFlags {
  return {
    comparison: env.VOICE_COMPARISON === "true",
    statusSpeech: env.VOICE_STATUS_SPEECH !== "false",
    ttsPrefetch: env.VOICE_TTS_PREFETCH === "true",
    sentenceChunks: env.VOICE_SENTENCE_CHUNKS === "true",
    pipelineMode: env.VOICE_PIPELINE_MODE === "sequential" ? "sequential" : "parallel",
  };
}

export const DEFAULT_VOICE_FLAGS: VoiceFlags = voiceFlagsFromEnv({});
