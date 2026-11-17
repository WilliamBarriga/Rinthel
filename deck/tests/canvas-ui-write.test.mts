import test from 'node:test';
import assert from 'node:assert/strict';
import { createMemoryStore } from '../server/src/store/memory/index.ts';
import { createCanvases, CanvasSpecError } from '../server/src/canvases.ts';
import { CanvasTools } from '../server/src/pi/canvas-tools.ts';

// `canvas_write` on a `ui` canvas, through the Agent's tools: the Agent hands over the whole spec,
// the catalog validates it and the state is the model's own. Domain level, on the in-memory store.
const store = createMemoryStore();
await store.sessions.create({ id: 's1', title: 'test', workspace: '/tmp', executor: 'host' });
function setup() {
  const canvases = createCanvases(store);
  const tools: Record<string, any> = {};
  new CanvasTools('s1', canvases).extension({ registerTool: (t: any) => (tools[t.name] = t) } as any);
  return { canvases, tools };
}
const value = (r: any) => JSON.parse(r.content[0].text);
const text = (content: string) => ({ root: 'a', elements: { a: { type: 'Text', props: { content }, children: [] } } });
async function uiCanvas(tools: Record<string, any>, title = 'Panel') {
  return value(await tools.canvas_create.execute('c', { title, kind: 'ui' }));
}
const write = (tools: Record<string, any>, id: string, row: any, spec: unknown, call = 'w') =>
  tools.canvas_write.execute(call, { canvas_id: row.id, revision: row.revision, operation: 'replace', spec });

test('the Agent creates a ui canvas and a valid spec is saved, bumping the revision', async () => {
  const { canvases, tools } = setup();
  const row = await uiCanvas(tools);
  assert.equal(row.kind, 'ui');
  const done = value(await write(tools, 'w', row, text('hola')));
  assert.equal(done.revision, row.revision + 1);
  const saved = await canvases.readCanvas('s1', row.id);
  assert.deepEqual(JSON.parse(saved.content).elements, text('hola').elements);
  assert.equal(saved.status, 'saved');
  assert.equal(saved.active_call, null);
});

test('an invalid spec is returned to the model as an error and nothing is saved', async () => {
  const { canvases, tools } = setup();
  const row = await uiCanvas(tools);
  value(await write(tools, 'ok', row, text('bueno')));
  const before = await canvases.readCanvas('s1', row.id);
  await assert.rejects(
    write(tools, 'bad', before, { root: 'a', elements: { a: { type: 'Html', props: { html: '<b>' }, children: [] } } }, 'bad'),
    /Html.*catálogo/s,
  );
  await assert.rejects(write(tools, 'bad2', before, { root: 'a' }, 'bad2'), /spec/);
  for (const children of [{ b: 1 }, null, 'b', 42, [1], ['b', null], ['ghost']]) {
    await assert.rejects(write(tools, 'children', before, {
      root: 'a', elements: { a: { type: 'Card', props: { title: 'x' }, children } },
    }, 'children'), (error: unknown) => {
      assert.ok(error instanceof CanvasSpecError);
      assert.equal(error.issues[0].code, 'structure');
      assert.equal(error.issues[0].element, 'a');
      return true;
    });
    const unchanged = await canvases.readCanvas('s1', row.id);
    assert.equal(unchanged.content, before.content);
    assert.equal(unchanged.revision, before.revision);
    assert.equal(unchanged.active_call, null);
  }
  const after = await canvases.readCanvas('s1', row.id);
  assert.equal(after.content, before.content);
  assert.equal(after.revision, before.revision);
  assert.equal(after.active_call, null);
  // The canvas is not stuck: the corrected spec goes through with the same revision.
  value(await write(tools, 'fix', after, text('corregido'), 'fix'));
});

test('the state of the spec is kept as the model wrote it', async () => {
  const { canvases, tools } = setup();
  const row = await uiCanvas(tools);
  const form = {
    root: 'f',
    state: { form: { name: '' } },
    elements: {
      f: { type: 'Stack', props: {}, children: ['name'] },
      name: { type: 'TextField', props: { label: 'Nombre', value: { $bindState: '/form/name' } } },
    },
  };
  value(await write(tools, 'w', row, form));
  assert.deepEqual(JSON.parse((await canvases.readCanvas('s1', row.id)).content).state, { form: { name: '' } });
});

test('a ui canvas takes a spec and a markdown canvas takes text', async () => {
  const { tools } = setup();
  const ui = await uiCanvas(tools);
  await assert.rejects(tools.canvas_write.execute('t', { canvas_id: ui.id, revision: ui.revision, operation: 'replace', content: '# hola' }), /spec/);
  await assert.rejects(tools.canvas_write.execute('a', { canvas_id: ui.id, revision: ui.revision, operation: 'append', spec: text('x') }), /replace/);
  const md = value(await tools.canvas_create.execute('m', { title: 'Notas' }));
  assert.equal(md.kind, 'markdown');
  await assert.rejects(tools.canvas_write.execute('s', { canvas_id: md.id, revision: md.revision, operation: 'replace', spec: text('x') }), /content/);
});

test('streamed text deltas never land in a ui canvas', async () => {
  const { canvases, tools } = setup();
  const controller = new CanvasTools('s1', canvases);
  const row = await uiCanvas(tools);
  controller.observe({ type: 'message_update', assistantMessageEvent: { type: 'toolcall_delta', contentIndex: 0, delta: `{"canvas_id":"${row.id}","revision":0,"operation":"replace","content":"{\\"root`, partial: { content: [{ type: 'toolCall', name: 'canvas_write', id: 'x' }] } } });
  await controller.idle();
  const after = await canvases.readCanvas('s1', row.id);
  assert.equal(after.content, '');
  assert.equal(after.active_call, null);
});

test('a stale revision is still refused for a spec', async () => {
  const { tools } = setup();
  const row = await uiCanvas(tools);
  value(await write(tools, 'one', row, text('uno'), 'one'));
  await assert.rejects(write(tools, 'two', row, text('dos'), 'two'), /current revision/);
});

test('the tool description teaches the model the catalog', () => {
  const { tools } = setup();
  assert.match(tools.canvas_write.description, /TextField/);
  assert.doesNotMatch(tools.canvas_write.description, /SourceCard|callTool|openDocument/);
  assert.match(tools.canvas_write.description, /spec/);
});
