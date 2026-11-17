/**
 * whisper-server and audiocpp-server as Deck reaches them, over real HTTP: the daemon's managed
 * services of the `stt` and `tts` Capabilities.
 *
 * whisper: `POST /inference` with a multipart `file` (WAV), `response_format=json` and `language`,
 * answering `{ text }` (https://github.com/ggml-org/whisper.cpp/tree/master/examples/server).
 * audio.cpp: `POST /v1/audio/speech` with `{ model, input, stream, stream_format, response_format }`,
 * answering raw PCM s16le with `X-Sample-Rate`, and `409` while it finishes the previous request.
 *
 * `requests` keeps what each one got, parsed, so a test can say what Deck sent.
 */
import { listen, readBody } from "./http-fake.mts";

export interface FakeWhisper {
  url: string;
  /** What the next transcriptions answer. */
  transcript: string;
  /** Answer with this status instead (`null`: answer normally). */
  failWith: number | null;
  requests: { language: string | null; responseFormat: string | null; bytes: number; riff: boolean }[];
  close(): Promise<void>;
}

export interface FakeAudio {
  url: string;
  /** PCM answered for each request, in chunks: 10 ms of silence per character of the input. */
  sampleRate: number;
  /** How many of the next requests answer `409` (busy) before one goes through. */
  busyFor: number;
  failWith: number | null;
  requests: { model: string; input: string; stream: boolean; responseFormat: string }[];
  close(): Promise<void>;
}

export async function fakeWhisper(transcript = " And so my fellow Americans. "): Promise<FakeWhisper> {
  const state = { transcript, failWith: null as number | null, requests: [] as FakeWhisper["requests"] };
  const server = await listen(async (req, res) => {
    if (req.method !== "POST" || req.url !== "/inference") { res.writeHead(404).end(); return; }
    // Parsed the way whisper-server does: a multipart form.
    const form = await new Request("http://x", { method: "POST", headers: { "content-type": req.headers["content-type"] ?? "" }, body: await readBody(req) }).formData();
    const file = form.get("file");
    const bytes = file instanceof Blob ? Buffer.from(await file.arrayBuffer()) : Buffer.alloc(0);
    state.requests.push({ language: form.get("language") as string | null, responseFormat: form.get("response_format") as string | null, bytes: bytes.length, riff: bytes.subarray(0, 4).toString("ascii") === "RIFF" });
    if (state.failWith) { res.writeHead(state.failWith, { "content-type": "application/json" }).end(JSON.stringify({ error: "whisper failed" })); return; }
    res.writeHead(200, { "content-type": "application/json" }).end(JSON.stringify({ text: state.transcript }));
  });
  return Object.assign(state, server);
}

export async function fakeAudio(sampleRate = 24000): Promise<FakeAudio> {
  const state = { sampleRate, busyFor: 0, failWith: null as number | null, requests: [] as FakeAudio["requests"] };
  const server = await listen(async (req, res) => {
    if (req.method !== "POST" || req.url !== "/v1/audio/speech") { res.writeHead(404).end(); return; }
    const json = JSON.parse((await readBody(req)).toString("utf8"));
    state.requests.push({ model: json.model, input: json.input, stream: json.stream, responseFormat: json.response_format });
    if (state.busyFor > 0) {
      state.busyFor--;
      res.writeHead(409, { "content-type": "application/json" }).end(JSON.stringify({ error: "busy" }));
      return;
    }
    if (state.failWith) { res.writeHead(state.failWith, { "content-type": "application/json" }).end(JSON.stringify({ error: "audio failed" })); return; }
    res.writeHead(200, { "content-type": "audio/pcm", "x-sample-rate": String(state.sampleRate) });
    const samples = Math.max(1, String(json.input).length) * (state.sampleRate / 100);
    const pcm = Buffer.alloc(samples * 2);
    // Two chunks: the audio streams as it is made.
    res.write(pcm.subarray(0, pcm.length / 2));
    res.end(pcm.subarray(pcm.length / 2));
  });
  return Object.assign(state, server);
}

/** The smallest WAV header plus a few samples: what the browser sends. */
export function tinyWav(samples = 160): Uint8Array<ArrayBuffer> {
  const data = Buffer.alloc(44 + samples * 2);
  data.write("RIFF"); data.writeUInt32LE(36 + samples * 2, 4); data.write("WAVEfmt ", 8);
  data.writeUInt32LE(16, 16); data.writeUInt16LE(1, 20); data.writeUInt16LE(1, 22);
  data.writeUInt32LE(16000, 24); data.writeUInt32LE(32000, 28); data.writeUInt16LE(2, 32); data.writeUInt16LE(16, 34);
  data.write("data", 36); data.writeUInt32LE(samples * 2, 40);
  return new Uint8Array(data);
}
