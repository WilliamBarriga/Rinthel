import test from 'node:test';
import assert from 'node:assert/strict';
import { createMemoryStore } from '../server/src/store/memory/index.ts';
import { createCanvases } from '../server/src/canvases.ts';
import { createCanvasActions, InMemorySessionNotes, CanvasActionError } from '../server/src/canvas-actions.ts';

// The one action of a Canvas `ui` that leaves the browser, «preguntar al agente», at domain level:
// the session notes are a double. The other actions of the catalog are local to the browser.
const store = createMemoryStore();
await store.sessions.create({ id: 's1', title: 'test', workspace: '/tmp', executor: 'host' });
const canvases = createCanvases(store);
const canvas = await canvases.createCanvas('s1', 'Panel', 'ui');

function setup() {
  const notes = new InMemorySessionNotes();
  return { actions: createCanvasActions({ canvases, notes }), notes };
}

test('«ask the agent» leaves the message in the Session, trimmed', async () => {
  const { actions, notes } = setup();
  const out = await actions.perform('s1', canvas.id, { action: 'askAgent', params: { message: ' explica esta tabla ' } });
  assert.deepEqual(out, { kind: 'asked' });
  assert.deepEqual(notes.notes, [{ sessionId: 's1', text: 'explica esta tabla' }]);
});

test('an invalid action, an empty message or a canvas of another Session is refused', async () => {
  const { actions, notes } = setup();
  await assert.rejects(actions.perform('s1', canvas.id, { action: 'setState', params: {} }), (e: any) => e.status === 400);
  await assert.rejects(actions.perform('s1', canvas.id, { action: 'askAgent', params: { message: '   ' } }), (e: any) => e.status === 400);
  await assert.rejects(actions.perform('s1', 'ghost', { action: 'askAgent', params: { message: 'hola' } }), (e: any) => e.status === 404);
  assert.deepEqual(notes.notes, []);
});

test('the actions that read a library or run a tool are gone: callTool and openDocument are refused', async () => {
  const { actions, notes } = setup();
  for (const action of ['callTool', 'openDocument']) {
    await assert.rejects(actions.perform('s1', canvas.id, { action, params: { tool: 'x', documentId: 'd' } }), (e: any) => e instanceof CanvasActionError && e.status === 400);
  }
  assert.deepEqual(notes.notes, []);
});

test('an action on a markdown canvas is refused as a 400, before any note', async () => {
  const { actions, notes } = setup();
  const doc = await canvases.createCanvas('s1', 'Notas', 'markdown');
  await assert.rejects(actions.perform('s1', doc.id, { action: 'askAgent', params: { message: 'hola' } }), (e: any) => e instanceof CanvasActionError && e.status === 400 && /ui/.test(e.message));
  assert.deepEqual(notes.notes, []);
});
