/**
 * Live transcription against a real whisper-server: opt-in, Linux, never in `npm test`.
 *
 *   RINTHEL_LIVE_WHISPER_URL=http://127.0.0.1:8178 npm run test:live-transcription
 *
 * The URL is the `stt` route of a running Instance (`GET /model-provider/routing`), or any
 * whisper-server started by hand. `tests/fixtures/jfk.wav` (16 kHz mono) is fed the way the browser
 * feeds it: in VAD frames to the live transcription, whose speculative and final requests go
 * through `DirectVoiceSpeech`, as Deck sends them. Without the variable every test is skipped.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { DirectVoiceSpeech } from '../../server/src/voice/direct-voice-speech.ts';
import { InMemoryModelRouting } from '../../server/src/model-routing/model-routing.ts';
import { LiveTranscription } from '../../web/src/voice/live-transcription.ts';
import { samplesWav } from '../../web/src/voice/speech-text.ts';

const URL_ = process.env.RINTHEL_LIVE_WHISPER_URL?.replace(/\/+$/, '');
const skip = URL_ ? false : 'RINTHEL_LIVE_WHISPER_URL is not set';
const EXPECTED = /ask not what your country can do for you/i;

/** The 16-bit PCM of a WAV as the browser's VAD hands it: floats in -1..1. */
function samplesOf(file: URL): Float32Array {
  const wav = readFileSync(file);
  let at = 12;
  while (at < wav.length) {
    const id = wav.toString('ascii', at, at + 4), size = wav.readUInt32LE(at + 4);
    if (id === 'data') {
      const samples = new Float32Array(size / 2);
      for (let i = 0; i < samples.length; i++) samples[i] = wav.readInt16LE(at + 8 + i * 2) / 32768;
      return samples;
    }
    at += 8 + size + (size % 2);
  }
  throw new Error('no data chunk');
}

function speech() {
  const routing = new InMemoryModelRouting();
  routing.set('stt', { url: URL_!, model: 'whisper', contextWindow: 0, reasoningFormat: 'none' });
  const direct = new DirectVoiceSpeech({ routing, busy: { retryMs: 500, waitMs: 5000, sleep: (ms) => new Promise((r) => setTimeout(r, ms)) } });
  return async (samples: Float32Array, signal: AbortSignal) =>
    direct.transcribe(new Uint8Array(await samplesWav(samples).arrayBuffer()), { language: 'en', signal });
}

test('whisper transcribes the recording Deck sends', { skip }, async () => {
  const text = await speech()(samplesOf(new URL('../fixtures/jfk.wav', import.meta.url)), AbortSignal.timeout(60000));
  assert.match(text, EXPECTED);
});

test('live transcription previews words before the turn ends, and the final text is the whole turn', { skip }, async () => {
  const samples = samplesOf(new URL('../fixtures/jfk.wav', import.meta.url));
  const previews: string[] = [];
  const live = new LiveTranscription(speech(), (text) => { if (text) previews.push(text); });
  const FRAME = 512;
  live.frame(0.9, samples.subarray(0, FRAME)); live.begin(); live.confirm();
  // Speech, then a pause long enough for a speculative request, then the rest of the recording.
  for (let at = FRAME; at < samples.length; at += FRAME) live.frame(0.9, samples.subarray(at, at + FRAME));
  for (let i = 0; i < 6; i++) live.frame(0.01, new Float32Array(FRAME));
  // The preview arrives while the person is still in the turn's closing silence.
  for (const deadline = Date.now() + 30000; !previews.length && Date.now() < deadline;) await new Promise((r) => setTimeout(r, 50));
  live.end(samples);
  const text = await live.finish(samples, AbortSignal.timeout(60000));
  assert.match(text, EXPECTED);
  assert.ok(previews.length > 0, 'a preview arrived before the final text');
});
