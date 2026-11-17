import type { VoiceConfig, VoiceSettings } from "@deck/contract";

/**
 * What `speak` answers: the audio of one phrase and how to read it. `pcm` is 24 kHz mono signed
 * 16-bit little-endian, and `streaming` says the server may still be producing it while it arrives
 * (the player may start from a cushion); anything else is `encoded` (a file the browser decodes
 * whole). `serverTiming` is the `Server-Timing` of the reply, for the profiler.
 */
export interface SpeechAudio {
  format: "pcm" | "encoded";
  streaming: boolean;
  body: ReadableStream<Uint8Array> | null;
  serverTiming: string;
}

/** What `transcribe` answers: the recognised text and the `Server-Timing` of the reply. */
export interface Transcription {
  text: string;
  serverTiming: string;
}

/**
 * Port: voice (`/api/voice` and `/api/sessions/:id/voice/*`), the only door the voice mode and the
 * Voz screen reach speech through. The adapter is the `fetch` one or the fake.
 *
 * `settings` is the reader's own settings plus whether the Instance has `stt` and `tts` active;
 * voice shows in a Session only with `enabled` and both. `saveConfig` writes the reader's own
 * settings and answers what was stored, `400` for an unsupported language, a detection value out of
 * range or a speech-end threshold not below the start one.
 *
 * `speak` and `transcribe` work in the reader's own Session and take the `signal` of the turn they
 * belong to: aborting it rejects with the signal's reason, an interruption and not a failure. A
 * refusal (`403` someone else's Session, `409` voice off or no active `stt`/`tts`, `400` a bad text
 * or recording, `502` a service down) rejects with a `PortError` whose message is the server's.
 * `speak` takes 1 to 600 characters; a busy TTS is waited for on the server.
 */
export interface VoiceSpeech {
  settings(): Promise<VoiceSettings>;
  saveConfig(config: VoiceConfig): Promise<Required<VoiceConfig>>;
  speak(sessionId: string, text: string, signal: AbortSignal): Promise<SpeechAudio>;
  transcribe(sessionId: string, wav: Blob, signal: AbortSignal): Promise<Transcription>;
}
