import type { VoiceConfig, VoiceSettings } from "@deck/contract";
import { globalFetch, kindOf, PortError, requestJson, type FetchLike } from "../http-errors";
import type { SpeechAudio, Transcription, VoiceSpeech } from "../voice-speech";

const voice = (sessionId: string) => `/api/sessions/${encodeURIComponent(sessionId)}/voice`;

async function refusal(res: Response): Promise<PortError> {
  const body: unknown = await res.json().catch(() => undefined);
  const error = (body as { error?: unknown } | undefined)?.error;
  return new PortError(kindOf(res.status), res.status, typeof error === "string" && error ? error : `HTTP ${res.status}`, body);
}

/** Aborting is the caller's decision, not a network failure: the signal's reason passes as it is. */
async function send(fetchImpl: FetchLike, url: string, init: RequestInit, signal: AbortSignal): Promise<Response> {
  signal.throwIfAborted();
  try {
    return await fetchImpl(url, { ...init, signal });
  } catch (e) {
    if (signal.aborted) throw signal.reason;
    throw new PortError("network", 0, e instanceof Error ? e.message : String(e));
  }
}

/** The `fetch` adapter only knows HTTP: URL, status, headers and body. */
export function fetchVoiceSpeech(fetchImpl: FetchLike = globalFetch): VoiceSpeech {
  return {
    settings: () => requestJson<VoiceSettings>(fetchImpl, "/api/voice"),
    saveConfig: (config) => requestJson<Required<VoiceConfig>>(fetchImpl, "/api/voice", { method: "PUT", body: JSON.stringify(config) }),
    async speak(sessionId, text, signal): Promise<SpeechAudio> {
      const res = await send(fetchImpl, `${voice(sessionId)}/speech`, { method: "POST", headers: { "Content-Type": "application/json", Accept: "audio/pcm" }, body: JSON.stringify({ text }) }, signal);
      if (!res.ok) throw await refusal(res);
      const pcm = res.headers.get("content-type")?.startsWith("audio/pcm") === true;
      if (pcm && res.headers.get("x-sample-rate") !== "24000") throw new PortError("http", res.status, "Audio de voz no admitido");
      return { format: pcm ? "pcm" : "encoded", streaming: pcm && res.headers.get("x-voice-streaming") === "true", body: res.body, serverTiming: res.headers.get("server-timing") ?? "" };
    },
    async transcribe(sessionId, wav, signal): Promise<Transcription> {
      const res = await send(fetchImpl, `${voice(sessionId)}/transcribe`, { method: "POST", headers: { "Content-Type": "audio/wav" }, body: wav }, signal);
      if (!res.ok) throw await refusal(res);
      const result = (await res.json()) as { text: string };
      return { text: result.text, serverTiming: res.headers.get("server-timing") ?? "" };
    },
  };
}
