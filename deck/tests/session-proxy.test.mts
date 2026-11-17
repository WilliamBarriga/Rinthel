import { after, test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, readdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { InMemoryModelRouting, type Route } from '../server/src/model-routing/model-routing.ts';
import { SessionProxy, type Prefill } from '../server/src/session-proxy.ts';
import { SessionSlots } from '../server/src/session-slots/session-slots.ts';
import { LlamaSlotStore } from '../server/src/session-slots/llama-slot-store.ts';
import { fakeLlama, type FakeLlama } from './helpers/fake-llama.mts';

/**
 * The one way a Session's pi reaches its Local model, at the seam pi sees: the Session's URL on the
 * proxy. Behind it a fake llama-server over real HTTP, the route as the daemon would give it, and the
 * real slot store over a temporary `--slot-save-path`.
 */
const roots: string[] = [];
after(() => { for (const r of roots) rmSync(r, { recursive: true, force: true }); });

async function setup({ maxBytes = 1_000_000 } = {}) {
  const dir = mkdtempSync(path.join(tmpdir(), 'deck-proxy-'));
  roots.push(dir);
  const llama = await fakeLlama(dir);
  const route = (model = 'qwen-a'): Route => ({ url: llama.url, model, contextWindow: 65536, reasoningFormat: 'qwen-chat-template' });
  const routing = new InMemoryModelRouting();
  routing.set('llm', route());
  const progress: { sessionId: string; prefill: Prefill }[] = [];
  const routes: { sessionId: string; model: string | null }[] = [];
  const slots = new SessionSlots(new LlamaSlotStore(dir), { maxBytes });
  const proxy = new SessionProxy({
    routing,
    slots,
    onProgress: (sessionId, prefill) => progress.push({ sessionId, prefill }),
    onRoute: (sessionId, r) => routes.push({ sessionId, model: r?.model ?? null }),
  });
  await proxy.start();
  return {
    dir, llama, routing, route, proxy, slots, progress, routes,
    files: () => readdirSync(dir).sort(),
    /** What llama-server saw once the last call's save has landed (pi has the stream before it). */
    settled: async () => { await slots.idle(); return llama.log; },
    close: async () => { proxy.stop(); await llama.close(); },
  };
}

const completion = (url: string, body: Record<string, unknown> = {}, signal?: AbortSignal) =>
  fetch(`${url}/v1/chat/completions`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: 'Bearer dummy' },
    body: JSON.stringify({ model: 'qwen-a', stream: true, messages: [{ role: 'user', content: 'hola' }], ...body }),
    signal,
  });

const saves = (llama: FakeLlama) => llama.log.filter((l) => l.startsWith('save'));

test("a Session's call goes straight to the route's llama-server, asking for progress, and pi gets the stream unchanged", async () => {
  const s = await setup();
  try {
    const access = await s.proxy.open('sess-1', 7);
    const res = await completion(access.url);
    assert.equal(res.status, 200);
    const text = await res.text();
    assert.match(text, /"content":"hola"/);
    assert.match(text, /prompt_progress/);
    assert.equal(s.llama.bodies[0].return_progress, true);
    assert.deepEqual(s.progress, [{ sessionId: 'sess-1', prefill: { total: 100, cache: 60, processed: 100, timeMs: 40 } }]);
    assert.equal(access.route()?.contextWindow, 65536);
  } finally { await s.close(); }
});

test("a Session's URL cannot be guessed from its id, and a closed Session reaches nothing", async () => {
  const s = await setup();
  try {
    const mine = await s.proxy.open('sess-1', 7);
    assert.ok(!mine.url.includes('sess-1'));
    const origin = new URL(mine.url).origin;
    assert.equal((await completion(`${origin}/s/sess-1`)).status, 404);
    s.proxy.close('sess-1');
    assert.equal((await completion(mine.url)).status, 404);
    assert.equal(s.llama.bodies.length, 0);
  } finally { await s.close(); }
});

test('a Session without an owner is refused before pi starts', async () => {
  const s = await setup();
  try {
    await assert.rejects(s.proxy.open('sess-1', null), /dueño/);
  } finally { await s.close(); }
});

test("each call restores the Session's slot before it and saves it after, named by owner, model and Session", async () => {
  const s = await setup();
  try {
    const one = await s.proxy.open('sess-1', 7);
    const other = await s.proxy.open('sess-2', 7);
    await (await completion(one.url)).text();
    await (await completion(one.url)).text();
    await (await completion(other.url)).text();
    await s.settled();
    const [first, second, third] = [s.llama.log.slice(0, 3), s.llama.log.slice(3, 6), s.llama.log.slice(6, 9)];
    assert.deepEqual(first.map((l) => l.split(' ')[0]), ['restore', 'completion', 'save']);
    // The same Session keeps its name; the second call restores what the first saved.
    assert.equal(first[0], second[0]);
    assert.equal(first[2], second[2]);
    assert.notEqual(third[0], first[0]);
    assert.equal(s.files().length, 2);
  } finally { await s.close(); }
});

test('the slot is held per HTTP request: a second call waits for the first to save, and a parallel call of the same Session does not deadlock', async () => {
  const s = await setup();
  try {
    const one = await s.proxy.open('sess-1', 7);
    const other = await s.proxy.open('sess-2', 7);
    const release = s.llama.hold();
    const a = completion(one.url).then((r) => r.text());
    await new Promise((r) => setTimeout(r, 50));
    const b = completion(other.url).then((r) => r.text());
    const c = completion(one.url).then((r) => r.text());
    await new Promise((r) => setTimeout(r, 50));
    // Only the first call has reached llama-server: the others wait for the slot.
    assert.equal(s.llama.log.filter((l) => l.startsWith('completion')).length, 1);
    release();
    await Promise.all([a, b, c]);
    await s.settled();
    const kinds = s.llama.log.map((l) => l.split(' ')[0]);
    assert.deepEqual(kinds, ['restore', 'completion', 'save', 'restore', 'completion', 'save', 'restore', 'completion', 'save']);
  } finally { await s.close(); }
});

test('a call llama-server fails, or one pi hangs up on, saves nothing and frees the slot', async () => {
  const s = await setup();
  try {
    const access = await s.proxy.open('sess-1', 7);
    s.llama.failWith = 500;
    assert.equal((await completion(access.url)).status, 500);
    s.llama.failWith = null;
    const release = s.llama.hold();
    const controller = new AbortController();
    const cut = completion(access.url, {}, controller.signal).catch(() => undefined);
    await new Promise((r) => setTimeout(r, 50));
    controller.abort();
    await cut;
    // The hang-up reaches the proxy before llama-server answers.
    await new Promise((r) => setTimeout(r, 50));
    release();
    await (await completion(access.url)).text();
    await s.settled();
    assert.equal(saves(s.llama).length, 1);
  } finally { await s.close(); }
});

test('when the Local model changes, the next call is told so (409 wrong_model) and the Session moves to the new route', async () => {
  const s = await setup();
  try {
    const access = await s.proxy.open('sess-1', 7);
    s.routing.set('llm', s.route('qwen-b'));
    const stale = await completion(access.url);
    assert.equal(stale.status, 409);
    assert.match(JSON.stringify(await stale.json()), /wrong_model/);
    assert.equal(access.route()?.model, 'qwen-b');
    assert.deepEqual(s.routes.at(-1), { sessionId: 'sess-1', model: 'qwen-b' });
    const fresh = await completion(access.url, { model: 'qwen-b' });
    assert.equal(fresh.status, 200);
    await fresh.text();
    assert.equal(s.llama.bodies.at(-1).model, 'qwen-b');
  } finally { await s.close(); }
});

test('with no active Local model the call is a 503 that says so, and a daemon that does not answer a 502', async () => {
  const s = await setup();
  try {
    const access = await s.proxy.open('sess-1', 7);
    s.routing.set('llm', null);
    const none = await completion(access.url);
    assert.equal(none.status, 503);
    assert.match(JSON.stringify(await none.json()), /Local model/);
    s.routing.down = true;
    assert.equal((await completion(access.url)).status, 502);
    assert.equal(s.llama.bodies.length, 0);
  } finally { await s.close(); }
});

test('saved slots stay under the byte budget: the least recently used go first, the one just saved stays', async () => {
  // Each fake slot is 64 bytes: room for two.
  const s = await setup({ maxBytes: 130 });
  try {
    const ids = ['a', 'b', 'c'];
    const sessions = await Promise.all(ids.map((id) => s.proxy.open(id, 7)));
    for (const access of sessions) await (await completion(access.url)).text();
    await (await completion(sessions[0].url)).text();
    await s.settled();
    assert.equal(s.files().length, 2);
    // `b` was the least recently used.
    const remaining = new Set(s.files());
    await s.slots.forget(7, 'b');
    assert.deepEqual(new Set(s.files()), remaining);
  } finally { await s.close(); }
});

test("forgetting a Session deletes its slots of every model, and nobody else's", async () => {
  const s = await setup();
  try {
    const mine = await s.proxy.open('sess-1', 7);
    await (await completion(mine.url)).text();
    s.routing.set('llm', s.route('qwen-b'));
    const theirs = await s.proxy.open('sess-2', 8);
    await (await completion(mine.url)).json();
    await (await completion(mine.url, { model: 'qwen-b' })).text();
    await (await completion(theirs.url, { model: 'qwen-b' })).text();
    await s.settled();
    assert.equal(s.files().length, 3);
    await s.slots.forget(7, 'sess-1');
    assert.equal(s.files().length, 1);
  } finally { await s.close(); }
});
