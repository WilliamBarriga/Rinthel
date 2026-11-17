import { after, test } from 'node:test';
import assert from 'node:assert/strict';
import { once, EventEmitter } from 'node:events';
import type { AddressInfo } from 'node:net';
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { FakeDaemon } from './helpers/fake-daemon.mts';
import { fakeAudio, fakeWhisper, tinyWav } from './helpers/fake-voice-services.mts';
import type { DeckSessions } from '../server/src/app.ts';
import { InMemorySessionRoots } from '../server/src/session-roots.ts';
import { InMemoryModelRouting } from '../server/src/model-routing/model-routing.ts';
import { DirectVoiceSpeech } from '../server/src/voice/direct-voice-speech.ts';

/**
 * Voice at Deck's HTTP surface (`createDeckApp`) over the in-memory store, the fake daemon, and a
 * fake whisper-server and audiocpp-server reached by `DirectVoiceSpeech` on the route: each user's
 * own settings, voice only in one's own Sessions, and nothing when the Instance has no `stt`/`tts`.
 */
const SECRET = 'voice-secret';
process.env.RINTHEL_PANEL_SECRET = SECRET;

const { createMemoryStore } = await import('../server/src/store/memory/index.ts');
const { createDeckApp } = await import('../server/src/app.ts');
const { ACCESS_COOKIE } = await import('../server/src/identity.ts');
const { daemonSessionIdentity } = await import('../server/src/daemon-session-identity.ts');
const { createCanvases } = await import('../server/src/canvases.ts');
const { createCanvasActions, storedSessionNotes } = await import('../server/src/canvas-actions.ts');
const { FsInstanceSoul } = await import('../server/src/instance-soul-fs.ts');

const root = mkdtempSync(path.join(tmpdir(), 'deck-voice-'));
const soulFile = path.join(root, 'instance', 'SOUL.md');
mkdirSync(path.dirname(soulFile), { recursive: true });
writeFileSync(soulFile, '# SOUL.md\n');

const whisper = await fakeWhisper(' And so my fellow Americans. ');
const audio = await fakeAudio();
const routing = new InMemoryModelRouting();
const route = (url: string, model: string) => ({ url, model, contextWindow: 0, reasoningFormat: 'none' });
const voiceOn = () => { routing.set('stt', route(whisper.url, 'whisper-base')); routing.set('tts', route(audio.url, 'pocket-tts')); };
voiceOn();

const store = createMemoryStore();
const daemon = new FakeDaemon(SECRET);
const ADMIN = daemon.addUser('root', 'root-password', 'admin');
const ANA = daemon.addUser('ana', 'ana-password');
const BEA = daemon.addUser('bea', 'bea-password');
const canvases = createCanvases(store);
const prompts: { id: string; message: string; options: unknown }[] = [];
const app = createDeckApp({
  store,
  daemon,
  identity: daemonSessionIdentity(daemon),
  serviceSecret: 'svc',
  sessions: Object.assign(new EventEmitter(), {
    stop: async () => {},
    isRunning: () => false,
    anyGenerating: () => false,
    liveSnapshot: () => [],
    prompt: async (id: string, message: string, options: unknown) => { prompts.push({ id, message, options }); return { queued: false, turnId: 't1' }; },
  }) as unknown as DeckSessions,
  roots: new InMemorySessionRoots(),
  slots: { forget: async () => {} },
  routing,
  canvases,
  canvasActions: createCanvasActions({ canvases, notes: storedSessionNotes(store) }),
  instanceSoul: new FsInstanceSoul(soulFile),
  voice: {
    speech: new DirectVoiceSpeech({ routing, busy: { retryMs: 1, waitMs: 5, sleep: async () => {} } }),
    flags: { statusSpeech: true, comparison: false, ttsPrefetch: false, sentenceChunks: false, pipelineMode: 'parallel' },
  },
  webDist: path.join(root, 'no-web'),
});
const server = app.listen(0, '127.0.0.1');
await once(server, 'listening');
const base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
after(async () => {
  server.closeAllConnections();
  await new Promise<void>((r) => server.close(() => r()));
  await whisper.close();
  await audio.close();
  rmSync(root, { recursive: true, force: true });
});

const cookie = (as: number) => `${ACCESS_COOKIE}=${daemon.accessToken(as)}`;
async function call(method: string, url: string, as: number, body?: unknown) {
  const res = await fetch(`${base}${url}`, {
    method,
    headers: { 'content-type': 'application/json', cookie: cookie(as) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  let json: any = text;
  try { json = JSON.parse(text); } catch { /* not JSON */ }
  return { status: res.status, body: json };
}
const transcribe = (id: string, as: number, wav: Uint8Array = tinyWav()) =>
  fetch(`${base}/api/sessions/${id}/voice/transcribe`, { method: 'POST', headers: { 'content-type': 'audio/wav', cookie: cookie(as) }, body: wav });
const speech = (id: string, as: number, text: unknown, accept = 'audio/pcm') =>
  fetch(`${base}/api/sessions/${id}/voice/speech`, { method: 'POST', headers: { 'content-type': 'application/json', accept, cookie: cookie(as) }, body: JSON.stringify({ text }) });

await store.sessions.create({ id: 'ana-chat', title: 'chat', workspace: '/w', executor: 'host', kind: 'agent', owner_user_id: ANA });
await store.sessions.create({ id: 'orphan', title: 'old', workspace: '/w', executor: 'host', kind: 'agent', owner_user_id: null });

test('a user starts with voice off, auto language and the default detection; the Instance says stt and tts are on', async () => {
  const { status, body } = await call('GET', '/api/voice', BEA);
  assert.equal(status, 200);
  assert.deepEqual({ enabled: body.enabled, language: body.language, stt: body.stt, tts: body.tts }, { enabled: false, language: 'auto', stt: true, tts: true });
  assert.equal(body.vad.redemptionMs, 1000);
  assert.equal(body.pipelineMode, 'parallel');
});

test('each user saves their own settings: a member\'s do not touch another\'s', async () => {
  const saved = await call('PUT', '/api/voice', ANA, { enabled: true, language: 'es', vad: { redemptionMs: 1500 } });
  assert.equal(saved.status, 200);
  assert.deepEqual([saved.body.enabled, saved.body.language, saved.body.vad.redemptionMs, saved.body.vad.minSpeechMs], [true, 'es', 1500, 256]);
  assert.equal((await call('GET', '/api/voice', ANA)).body.language, 'es');
  assert.equal((await call('GET', '/api/voice', BEA)).body.enabled, false);
});

test('settings out of range are a 400 and nothing is saved', async () => {
  for (const bad of [{ enabled: 'yes' }, { enabled: true, language: 'xx' }, { enabled: true, vad: { redemptionMs: 10 } }, { enabled: true, vad: { negativeSpeechThreshold: 0.9 } }]) {
    assert.equal((await call('PUT', '/api/voice', BEA, bad)).status, 400, JSON.stringify(bad));
  }
  assert.equal((await call('GET', '/api/voice', BEA)).body.enabled, false);
});

test('the owner transcribes in their Session: whisper gets the WAV in the owner\'s language', async () => {
  whisper.requests.length = 0;
  const res = await transcribe('ana-chat', ANA);
  assert.equal(res.status, 200);
  assert.deepEqual(await res.json(), { text: 'And so my fellow Americans.' });
  assert.equal(whisper.requests[0].language, 'es');
});

test('the owner hears a reply: streamed PCM with its rate, or one WAV', async () => {
  audio.requests.length = 0;
  const pcm = await speech('ana-chat', ANA, 'Hola');
  assert.equal(pcm.status, 200);
  assert.equal(pcm.headers.get('content-type'), 'audio/pcm');
  assert.equal(pcm.headers.get('x-sample-rate'), '24000');
  assert.equal((await pcm.arrayBuffer()).byteLength, 4 * 240 * 2);
  assert.deepEqual(audio.requests.map((r) => r.model), ['pocket-tts']);
  const wav = await speech('ana-chat', ANA, 'Hola', 'audio/wav');
  assert.equal(wav.headers.get('content-type'), 'audio/wav');
  assert.equal(Buffer.from(await wav.arrayBuffer()).subarray(0, 4).toString(), 'RIFF');
});

test('someone else\'s Session is a 403, an admin\'s too; one without owner as well; an unknown one 404', async () => {
  await call('PUT', '/api/voice', BEA, { enabled: true });
  await call('PUT', '/api/voice', ADMIN, { enabled: true });
  assert.equal((await transcribe('ana-chat', BEA)).status, 403);
  assert.equal((await speech('ana-chat', BEA, 'hola')).status, 403);
  assert.equal((await transcribe('ana-chat', ADMIN)).status, 403);
  assert.equal((await speech('orphan', ADMIN, 'hola')).status, 403);
  assert.equal((await transcribe('nope', ANA)).status, 404);
  await call('PUT', '/api/voice', BEA, { enabled: false });
});

test('with the reader\'s voice off the routes are a 409', async () => {
  await store.sessions.create({ id: 'bea-chat', title: 'chat', workspace: '/w', executor: 'host', kind: 'agent', owner_user_id: BEA });
  assert.equal((await transcribe('bea-chat', BEA)).status, 409);
  assert.equal((await speech('bea-chat', BEA, 'hola')).status, 409);
});

test('without an active stt or tts the Instance says so and the routes are a 409, not a 502', async () => {
  routing.set('tts', null);
  try {
    const settings = (await call('GET', '/api/voice', ANA)).body;
    assert.deepEqual([settings.stt, settings.tts], [true, false]);
    const res = await speech('ana-chat', ANA, 'hola');
    assert.equal(res.status, 409);
    assert.match((await res.json()).error, /tts/);
  } finally { voiceOn(); }
});

test('a bad recording or text is a 400; a service down is a 502', async () => {
  assert.equal((await transcribe('ana-chat', ANA, new Uint8Array([1, 2, 3]))).status, 400);
  assert.equal((await speech('ana-chat', ANA, '')).status, 400);
  assert.equal((await speech('ana-chat', ANA, 'x'.repeat(601))).status, 400);
  whisper.failWith = 500;
  try { assert.equal((await transcribe('ana-chat', ANA)).status, 502); } finally { whisper.failWith = null; }
});

test('a prompt sent from voice mode reaches the Session as a voice Turn; a typed one does not', async () => {
  prompts.length = 0;
  await call('POST', '/api/sessions/ana-chat/prompt', ANA, { message: 'hola', voice: true });
  await call('POST', '/api/sessions/ana-chat/prompt', ANA, { message: 'escrito' });
  assert.deepEqual(prompts.map((p) => (p.options as { voice?: boolean }).voice === true), [true, false]);
});
