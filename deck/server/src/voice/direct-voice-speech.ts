import type { ModelRouting, Route } from "../model-routing/model-routing.js";
import { SPEECH_SAMPLE_RATE, VoiceSpeechError, capabilityOff, type SpeechAvailability, type SpeechStream, type VoiceSpeech } from "./voice-speech.js";

/**
 * Speech straight to the daemon's managed services, on the route `GET /model-provider/routing` gives
 * (ADR 0008): whisper-server for `stt` (`POST /inference`) and audiocpp-server for `tts`
 * (`POST /v1/audio/speech`). The route is read on every call, so a Local model the admin switches
 * on or off applies to the next one. The TTS speaks in its Local model's fixed voice: no voice is sent.
 *
 * whisper-server: https://github.com/ggml-org/whisper.cpp/tree/master/examples/server
 */

/** How a busy audio.cpp is waited for. The composition gives the real clock, a test a virtual one. */
export interface BusyPolicy {
  /** How long to wait before asking a busy TTS again. */
  retryMs: number;
  /** How long a busy TTS is waited for in all. */
  waitMs: number;
  sleep(ms: number, signal?: AbortSignal): Promise<void>;
}

export interface DirectVoiceSpeechDeps {
  routing: ModelRouting;
  busy: BusyPolicy;
  /** The HTTP client; the global `fetch` by default. */
  fetch?: typeof fetch;
}

export class DirectVoiceSpeech implements VoiceSpeech {
  private readonly fetch: typeof fetch;

  constructor(private readonly deps: DirectVoiceSpeechDeps) {
    this.fetch = deps.fetch ?? fetch;
  }

  async available(): Promise<SpeechAvailability> {
    const on = async (capability: "stt" | "tts") => (await this.deps.routing.read(capability).catch(() => null)) !== null;
    const [stt, tts] = await Promise.all([on("stt"), on("tts")]);
    return { stt, tts };
  }

  async transcribe(wav: Uint8Array<ArrayBuffer>, { language, signal }: { language: string; signal?: AbortSignal }): Promise<string> {
    signal?.throwIfAborted();
    const route = await this.route("stt");
    // whisper.cpp's multipart; fetch sets its content-type with the boundary.
    const form = new FormData();
    form.set("file", new Blob([wav], { type: "audio/wav" }), "recording.wav");
    form.set("response_format", "json");
    form.set("language", language);
    const res = await this.fetch(`${route.url}/inference`, { method: "POST", body: form, redirect: "error", signal });
    if (!res.ok) throw new Error(`El STT respondió HTTP ${res.status}`);
    const result = (await res.json()) as { text?: unknown };
    if (typeof result.text !== "string") throw new Error("El STT no devolvió una transcripción");
    return result.text.trim();
  }

  /** audio.cpp answers 409 while it finishes the previous request: asked again until `busy.waitMs` has been slept. */
  async speak(text: string, { signal }: { signal?: AbortSignal } = {}): Promise<SpeechStream> {
    signal?.throwIfAborted();
    const route = await this.route("tts");
    const { busy } = this.deps;
    let waited = 0;
    while (true) {
      const res = await this.fetch(`${route.url}/v1/audio/speech`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ model: route.model, input: text, stream: true, stream_format: "audio", response_format: "pcm" }),
        redirect: "error",
        signal,
      });
      if (res.status === 409) {
        await res.body?.cancel();
        if (waited + busy.retryMs > busy.waitMs) throw new VoiceSpeechError(503, "El TTS está ocupado con otra petición; inténtalo en un momento.");
        await busy.sleep(busy.retryMs, signal);
        waited += busy.retryMs;
        continue;
      }
      if (!res.ok) throw new Error(`El TTS respondió HTTP ${res.status}`);
      if (!res.body) throw new Error("El TTS no devolvió audio");
      const rate = Number(res.headers.get("x-sample-rate"));
      return { sampleRate: Number.isInteger(rate) && rate > 0 ? rate : SPEECH_SAMPLE_RATE, pcm: res.body };
    }
  }

  private async route(capability: "stt" | "tts"): Promise<Route> {
    const route = await this.deps.routing.read(capability);
    if (!route) throw capabilityOff(capability);
    return route;
  }
}
