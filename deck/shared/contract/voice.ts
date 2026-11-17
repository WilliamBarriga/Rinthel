/**
 * Voz: what Node's `/api/voice` and `/api/sessions/:id/voice/*` tell the front. Types only.
 */

/** Speech detection (Silero VAD in the browser): when a turn starts and ends. */
export interface VoiceVad {
  positiveSpeechThreshold: number;
  negativeSpeechThreshold: number;
  minSpeechMs: number;
  preSpeechPadMs: number;
  redemptionMs: number;
}

/** One user's voice settings (`PUT /api/voice`, the reader's own): whether the controls show, the input language and the detection. */
export interface VoiceConfig {
  enabled: boolean;
  /** A code whisper accepts, or `auto`. */
  language?: string;
  vad?: VoiceVad;
}

/** The `VOICE_*` switches of the Instance's pipeline, read by the server at boot. */
export interface VoiceFlags {
  statusSpeech: boolean;
  comparison: boolean;
  ttsPrefetch: boolean;
  sentenceChunks: boolean;
  pipelineMode: "sequential" | "parallel";
}

/**
 * `GET /api/voice`: the reader's settings, the switches, and whether the Instance has `stt` and `tts`
 * active now. Voice shows in a Session only with `enabled` and both on.
 */
export interface VoiceSettings extends Required<VoiceConfig>, VoiceFlags {
  stt: boolean;
  tts: boolean;
}
