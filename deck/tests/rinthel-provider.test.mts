import { after, test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { InMemoryModelRouting, type Route } from '../server/src/model-routing/model-routing.ts';
import { SessionProxy } from '../server/src/session-proxy.ts';
import { SessionSlots } from '../server/src/session-slots/session-slots.ts';
import { InMemorySlotStore } from '../server/src/session-slots/slot-store.ts';
import { rinthelProvider, routedModel } from '../server/src/pi/rinthel-provider.ts';
import { fakeLlama } from './helpers/fake-llama.mts';

/**
 * pi's only provider, driven the way pi drives it (`streamSimple`), against the Session's proxy and
 * a fake llama-server: the model is the route's, with the route's window, and a Local model switched
 * mid-Session moves the turn to the new one instead of failing it.
 */
const roots: string[] = [];
after(() => { for (const r of roots) rmSync(r, { recursive: true, force: true }); });

async function setup() {
  const dir = mkdtempSync(path.join(tmpdir(), 'deck-provider-'));
  roots.push(dir);
  const llama = await fakeLlama(dir);
  const route = (model: string, contextWindow = 65536): Route => ({ url: llama.url, model, contextWindow, reasoningFormat: 'qwen-chat-template' });
  const routing = new InMemoryModelRouting();
  routing.set('llm', route('qwen-a'));
  const proxy = new SessionProxy({ routing, slots: new SessionSlots(new InMemorySlotStore(), { maxBytes: 10 }), onProgress: () => {}, onRoute: () => {} });
  await proxy.start();
  const access = await proxy.open('sess-1', 7);
  const switched: string[] = [];
  const provider = rinthelProvider(access, async (model) => { switched.push(model.id); });
  return { llama, routing, route, access, provider, switched, close: async () => { proxy.stop(); await llama.close(); } };
}

const context = { messages: [{ role: 'user' as const, content: 'hola', timestamp: 0 }] };

async function answer(provider: ReturnType<typeof rinthelProvider>, model = provider.getModels()[0]): Promise<{ text: string; types: string[] }> {
  const types: string[] = [];
  let text = '';
  for await (const event of provider.streamSimple!(model, context as any, { apiKey: 'dummy' } as any)) {
    types.push(event.type);
    if (event.type === 'text_delta') text += event.delta;
    if (event.type === 'error') text += `[error ${(event as any).error?.errorMessage}]`;
  }
  return { text, types };
}

test("the model pi runs is the route's, with the route's context window and reasoning format", () => {
  const model = routedModel('http://127.0.0.1:1/s/x', { url: 'http://llama', model: 'qwen-a', contextWindow: 32768, reasoningFormat: 'deepseek' });
  assert.equal(model.id, 'qwen-a');
  assert.equal(model.baseUrl, 'http://127.0.0.1:1/s/x/v1');
  assert.equal(model.contextWindow, 32768);
  assert.ok(model.maxTokens <= 32768);
  assert.equal((model as any).compat.thinkingFormat, 'deepseek');
});

test('a turn on the current Local model streams its answer', async () => {
  const s = await setup();
  try {
    const { text } = await answer(s.provider);
    assert.equal(text, 'hola');
    assert.equal(s.llama.bodies[0].model, 'qwen-a');
    assert.deepEqual(s.switched, []);
  } finally { await s.close(); }
});

test('a Local model switched since the last call: the Session moves to it and the turn goes again, as one turn', async () => {
  const s = await setup();
  try {
    s.routing.set('llm', s.route('qwen-b', 131072));
    const { text, types } = await answer(s.provider);
    assert.equal(text, 'hola');
    assert.deepEqual(s.switched, ['qwen-b']);
    assert.equal(s.llama.bodies.at(-1).model, 'qwen-b');
    assert.equal(types.filter((t) => t === 'start').length, 1);
    assert.equal(s.provider.getModels()[0].contextWindow, 131072);
  } finally { await s.close(); }
});

test('with no Local model the turn fails with the reason, once', async () => {
  const s = await setup();
  try {
    s.routing.set('llm', null);
    const { text } = await answer(s.provider);
    assert.match(text, /Local model/);
    assert.deepEqual(s.switched, []);
  } finally { await s.close(); }
});
