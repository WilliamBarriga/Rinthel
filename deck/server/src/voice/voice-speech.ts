/**
 * Speech for voice: speech-to-text and text-to-speech behind one seam. The voice routes
 * (`api/voice.ts`) know only this interface; where the audio is made is an adapter's business:
 * `DirectVoiceSpeech` (straight to whisper-server and audiocpp-server, on the daemon's route) or
 * `FakeVoiceSpeech`.
 *
 * Interface: no call picks a model or a voice (the Instance has one Local model per Capability, with
 * its fixed voice). A failure is a `VoiceSpeechError` carrying the HTTP status the caller should show
 * (409 when the Capability has no active Local model, 503 when the TTS stays busy) or any other `Error`
 * for a plain 502. `signal` cancels the call and, for `speak`, the stream that came out of it.
 */

/** The TTS's sample rate as Deck expects it: 24 kHz mono s16le, what the catalog's TTS makes. */
export const SPEECH_SAMPLE_RATE = 24000;

/** Synthesized audio: raw PCM, signed 16-bit little-endian, mono, as it is made. */
export interface SpeechStream {
  sampleRate: number;
  pcm: ReadableStream<Uint8Array>;
}

/** Which Capabilities have an active Local model now. */
export interface SpeechAvailability {
  stt: boolean;
  tts: boolean;
}

export interface VoiceSpeech {
  /** Never throws: a daemon that does not answer is nothing available. */
  available(): Promise<SpeechAvailability>;
  /** The transcript of a WAV recording, trimmed. `language` is a code the voice settings accept, or `auto`. */
  transcribe(wav: Uint8Array<ArrayBuffer>, options: { language: string; signal?: AbortSignal }): Promise<string>;
  /** Speaks `text`; the audio can start flowing before synthesis ends. */
  speak(text: string, options?: { signal?: AbortSignal }): Promise<SpeechStream>;
}

/** A failure with its own status and a reason the user can read, instead of the 502 the rest get. */
export class VoiceSpeechError extends Error {
  constructor(readonly status: number, message: string) {
    super(message);
  }
}

/** What the user reads when a Capability has no active Local model. */
export function capabilityOff(capability: "stt" | "tts"): VoiceSpeechError {
  return new VoiceSpeechError(409, `La Instance no tiene un Local model de ${capability} activo: un admin puede activarlo.`);
}

type Op = "transcribe" | "speak";

/**
 * The test double: answers a fixed transcript and a fixed PCM, logs every call, and answers as an
 * Instance whose `stt`/`tts` are on or off as told. `failNext(op, error)` makes the next call of that
 * method reject, as a service that is down would.
 */
export class FakeVoiceSpeech implements VoiceSpeech {
  readonly calls: { op: Op; text?: string; language?: string; bytes?: number }[] = [];
  private readonly failures: { op: Op; error: Error }[] = [];
  private on: SpeechAvailability;

  constructor(private readonly answer: { transcript?: string; pcm?: Uint8Array; stt?: boolean; tts?: boolean } = {}) {
    this.on = { stt: answer.stt ?? true, tts: answer.tts ?? true };
  }

  /** Turns a Capability on or off, as the admin would. */
  set(capability: "stt" | "tts", on: boolean): void {
    this.on = { ...this.on, [capability]: on };
  }

  failNext(op: Op, error: Error): void {
    this.failures.push({ op, error });
  }

  async available(): Promise<SpeechAvailability> {
    return { ...this.on };
  }

  async transcribe(wav: Uint8Array<ArrayBuffer>, { language, signal }: { language: string; signal?: AbortSignal }): Promise<string> {
    signal?.throwIfAborted();
    this.check("transcribe", "stt");
    this.calls.push({ op: "transcribe", language, bytes: wav.length });
    return (this.answer.transcript ?? "texto de prueba").trim();
  }

  async speak(text: string, { signal }: { signal?: AbortSignal } = {}): Promise<SpeechStream> {
    signal?.throwIfAborted();
    this.check("speak", "tts");
    this.calls.push({ op: "speak", text });
    const pcm = this.answer.pcm ?? new Uint8Array([0, 0, 255, 127]);
    return {
      sampleRate: SPEECH_SAMPLE_RATE,
      pcm: new ReadableStream<Uint8Array>({
        start(controller) {
          if (signal?.aborted) return controller.error(signal.reason);
          controller.enqueue(pcm);
          controller.close();
        },
      }),
    };
  }

  private check(op: Op, capability: "stt" | "tts"): void {
    const at = this.failures.findIndex((f) => f.op === op);
    if (at >= 0) throw this.failures.splice(at, 1)[0].error;
    if (!this.on[capability]) throw capabilityOff(capability);
  }
}
