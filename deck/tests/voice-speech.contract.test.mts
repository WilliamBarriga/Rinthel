import { after, describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { FakeVoiceSpeech, VoiceSpeechError, type VoiceSpeech } from '../server/src/voice/voice-speech.ts';
import { DirectVoiceSpeech } from '../server/src/voice/direct-voice-speech.ts';
import { InMemoryModelRouting } from '../server/src/model-routing/model-routing.ts';
import { fakeAudio, fakeWhisper, tinyWav } from './helpers/fake-voice-services.mts';

/**
 * The `VoiceSpeech` contract: what the voice routes rely on, run against the double and against
 * `DirectVoiceSpeech` over a fake whisper-server and a fake audiocpp-server on real HTTP, reached by
 * the route the daemon gives (`InMemoryModelRouting` plays `GET /model-provider/routing`).
 */
const whisper = await fakeWhisper(' And so my fellow Americans. ');
const audio = await fakeAudio();
after(async () => { await whisper.close(); await audio.close(); });

const route = (url: string, model: string) => ({ url, model, contextWindow: 0, reasoningFormat: 'none' });
/** A busy audio.cpp is asked again at once, a test does not wait for real. */
const instantBusy = (waitMs = 3) => ({ retryMs: 1, waitMs, sleep: async () => {} });

async function bytesOf(pcm: ReadableStream<Uint8Array>): Promise<number> {
  let total = 0;
  for await (const chunk of pcm) total += chunk.length;
  return total;
}

function voiceSpeechContract(name: string, make: (on: { stt: boolean; tts: boolean }) => VoiceSpeech) {
  describe(`VoiceSpeech: ${name}`, () => {
    const live = () => new AbortController().signal;

    test('available says which of stt and tts have an active Local model', async () => {
      assert.deepEqual(await make({ stt: true, tts: true }).available(), { stt: true, tts: true });
      assert.deepEqual(await make({ stt: true, tts: false }).available(), { stt: true, tts: false });
    });

    test('transcribe answers the recognised text, trimmed', async () => {
      assert.equal(await make({ stt: true, tts: true }).transcribe(tinyWav(), { language: 'en', signal: live() }), 'And so my fellow Americans.');
    });

    test('speak answers PCM s16le at 24 kHz, read whole', async () => {
      const { sampleRate, pcm } = await make({ stt: true, tts: true }).speak('Hola, ¿qué tal?', { signal: live() });
      assert.equal(sampleRate, 24000);
      const bytes = await bytesOf(pcm);
      assert.ok(bytes > 0 && bytes % 2 === 0);
    });

    test('a Capability with no active Local model is a 409 the user can read, not a 502', async () => {
      const off = make({ stt: false, tts: false });
      await assert.rejects(off.transcribe(tinyWav(), { language: 'auto', signal: live() }), (e: unknown) => e instanceof VoiceSpeechError && e.status === 409 && /stt/.test(e.message));
      await assert.rejects(off.speak('hola', { signal: live() }), (e: unknown) => e instanceof VoiceSpeechError && e.status === 409 && /tts/.test(e.message));
    });

    test('an aborted signal rejects without reaching the service', async () => {
      const controller = new AbortController();
      controller.abort(new Error('barge-in'));
      const voice = make({ stt: true, tts: true });
      await assert.rejects(voice.transcribe(tinyWav(), { language: 'auto', signal: controller.signal }), /barge-in/);
      await assert.rejects(voice.speak('hola', { signal: controller.signal }), /barge-in/);
    });
  });
}

voiceSpeechContract('FakeVoiceSpeech', (on) => new FakeVoiceSpeech({ transcript: ' And so my fellow Americans. ', ...on }));
voiceSpeechContract('DirectVoiceSpeech', (on) => {
  const routing = new InMemoryModelRouting();
  if (on.stt) routing.set('stt', route(whisper.url, 'whisper-base'));
  if (on.tts) routing.set('tts', route(audio.url, 'pocket-tts'));
  return new DirectVoiceSpeech({ routing, busy: instantBusy() });
});

describe('DirectVoiceSpeech', () => {
  const live = () => new AbortController().signal;
  const direct = (busy = instantBusy()) => {
    const routing = new InMemoryModelRouting();
    routing.set('stt', route(whisper.url, 'whisper-base'));
    routing.set('tts', route(audio.url, 'pocket-tts'));
    return { routing, speech: new DirectVoiceSpeech({ routing, busy }) };
  };

  test('whisper gets the WAV as a multipart file, JSON answers and the language', async () => {
    whisper.requests.length = 0;
    await direct().speech.transcribe(tinyWav(), { language: 'es', signal: live() });
    assert.deepEqual(whisper.requests, [{ language: 'es', responseFormat: 'json', bytes: tinyWav().length, riff: true }]);
  });

  test('audio.cpp is asked for the route\'s model, streamed PCM', async () => {
    audio.requests.length = 0;
    await bytesOf((await direct().speech.speak('Hola', { signal: live() })).pcm);
    assert.deepEqual(audio.requests, [{ model: 'pocket-tts', input: 'Hola', stream: true, responseFormat: 'pcm' }]);
  });

  test('the route is read on every call: a Local model the admin switched off stops the next one', async () => {
    const { routing, speech } = direct();
    await speech.transcribe(tinyWav(), { language: 'auto', signal: live() });
    routing.set('stt', null);
    await assert.rejects(speech.transcribe(tinyWav(), { language: 'auto', signal: live() }), (e: unknown) => e instanceof VoiceSpeechError && e.status === 409);
  });

  test('a busy audio.cpp (409) is asked again until it answers', async () => {
    audio.busyFor = 2;
    audio.requests.length = 0;
    const { pcm } = await direct().speech.speak('Hola', { signal: live() });
    assert.ok(await bytesOf(pcm) > 0);
    assert.equal(audio.requests.length, 3);
  });

  test('busy for longer than the wait is a 503', async () => {
    audio.busyFor = 10;
    try {
      await assert.rejects(direct(instantBusy(2)).speech.speak('Hola', { signal: live() }), (e: unknown) => e instanceof VoiceSpeechError && e.status === 503);
    } finally { audio.busyFor = 0; }
  });

  test('a failing service is a plain error (the route answers 502), with its status', async () => {
    whisper.failWith = 500;
    try {
      await assert.rejects(direct().speech.transcribe(tinyWav(), { language: 'auto', signal: live() }), (e: unknown) => !(e instanceof VoiceSpeechError) && /500/.test((e as Error).message));
    } finally { whisper.failWith = null; }
  });

  test('a sample rate other than audio.cpp\'s 24 kHz is said as it is', async () => {
    audio.sampleRate = 16000;
    try {
      assert.equal((await direct().speech.speak('Hola', { signal: live() })).sampleRate, 16000);
    } finally { audio.sampleRate = 24000; }
  });

  test('a daemon that does not answer the routing is an error, and available says nothing is there', async () => {
    const { routing, speech } = direct();
    routing.down = true;
    await assert.rejects(speech.transcribe(tinyWav(), { language: 'auto', signal: live() }), /routing unavailable/);
    assert.deepEqual(await speech.available(), { stt: false, tts: false });
  });
});
