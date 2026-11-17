import { test } from 'node:test';
import assert from 'node:assert/strict';
import { COMPONENT_NAMES, ACTION_NAMES, validateCanvasSpec, canvasCatalogPrompt, canvasActionParams } from '../shared/canvas-catalog/index.ts';

/**
 * The catalog is the contract between the model, the server (`canvas_write`)
 * and the front (component registry). These tests cross its one interface:
 * `validateCanvasSpec` over fixed specs, no app and no renderer.
 */
const one = (type: string, props: Record<string, unknown>, extra: Record<string, unknown> = {}) =>
  ({ root: 'a', elements: { a: { type, props, children: [], ...extra } } });

test('a valid fixed spec of every component passes', () => {
  const specs = [
    one('Heading', { text: 'Resumen', level: 2 }),
    one('Text', { content: 'Hola **mundo**' }),
    one('Table', { columns: [{ key: 'name', label: 'Nombre' }], rows: [{ name: 'a' }], filter: null }),
    one('Metric', { label: 'Total', value: 42, detail: null }),
    one('Card', { title: 'Datos' }),
    one('Stack', { direction: 'horizontal', gap: null }),
    one('Button', { label: 'Abrir', variant: 'primary' }, { on: { press: { action: 'setState', params: { statePath: '/x', value: 1 } } } }),
    one('TextField', { label: 'Nombre', value: { $bindState: '/form/name' }, placeholder: null, inputType: 'text' }),
    one('SelectField', { label: 'Tipo', value: { $bindState: '/form/kind' }, options: [{ value: 'a', label: 'A' }] }),
    one('CheckboxField', { label: 'Activo', value: { $bindState: '/form/on' } }),
  ];
  for (const spec of specs) assert.equal(validateCanvasSpec(spec).ok, true, JSON.stringify(spec));
});

test('state and repeat expressions are accepted where a value goes', () => {
  const spec = {
    root: 'list',
    state: { items: [{ title: 'Manual', excerpt: 'x' }] },
    elements: {
      list: { type: 'Stack', props: { direction: null, gap: null }, children: ['src'], repeat: { statePath: '/items' } },
      src: { type: 'Text', props: { content: { $item: 'title' } }, children: [] },
      table: { type: 'Table', props: { columns: [{ key: 'a', label: 'A' }], rows: { $state: '/rows' }, filter: { $bindState: '/q' } }, children: [] },
    },
  };
  const result = validateCanvasSpec(spec);
  assert.equal(result.ok, true, JSON.stringify(result));
});

test('a component outside the catalog is rejected and named', () => {
  for (const type of ['Html', 'Link', 'Chart', 'shadcn.Button']) {
    const result = validateCanvasSpec(one(type, {}));
    assert.equal(result.ok, false, type);
    if (!result.ok) {
      assert.equal(result.issues[0].code, 'unknown_component');
      assert.equal(result.issues[0].element, 'a');
      assert.match(result.issues[0].message, new RegExp(type.replace('.', '\\.')));
    }
  }
});

test('props that break a component schema are rejected with the element and prop', () => {
  const result = validateCanvasSpec(one('Heading', { text: 5, level: 9 }));
  assert.equal(result.ok, false);
  if (!result.ok) {
    assert.ok(result.issues.every((i) => i.code === 'invalid_props' && i.element === 'a'));
    assert.deepEqual(result.issues.map((i) => i.path).sort(), ['level', 'text']);
  }
});

test('unknown props are rejected so the model cannot smuggle in markup', () => {
  const result = validateCanvasSpec(one('Text', { content: 'x', dangerouslySetInnerHTML: '<b>' }));
  assert.equal(result.ok, false);
});

test('an unknown action in an event handler is rejected', () => {
  const result = validateCanvasSpec(one('Button', { label: 'x', variant: null }, { on: { press: { action: 'runTool', params: {} } } }));
  assert.equal(result.ok, false);
  if (!result.ok) assert.equal(result.issues[0].code, 'unknown_action');
});

test('openDocument, callTool and SourceCard are not in the catalog', () => {
  assert.equal(COMPONENT_NAMES.includes('SourceCard' as never), false);
  for (const action of ['openDocument', 'callTool']) {
    assert.equal(ACTION_NAMES.includes(action as never), false, action);
    assert.equal(validateCanvasSpec(one('Button', { label: 'x', variant: null }, { on: { press: { action, params: {} } } })).ok, false, action);
  }
});

test('structural errors are reported: missing root and dangling children', () => {
  const noRoot = validateCanvasSpec({ root: 'zzz', elements: { a: { type: 'Text', props: { content: 'x' }, children: [] } } });
  assert.equal(noRoot.ok, false);
  const dangling = validateCanvasSpec({ root: 'a', elements: { a: { type: 'Card', props: { title: null }, children: ['ghost'] } } });
  assert.equal(dangling.ok, false);
  if (!dangling.ok) assert.equal(dangling.issues[0].code, 'structure');
});

test('malformed children return a structural error instead of throwing', () => {
  for (const children of [{ b: 1 }, null, 'b', 42, [1], ['b', null]]) {
    const result = validateCanvasSpec({ root: 'a', elements: { a: { type: 'Card', props: { title: 'x' }, children } } });
    assert.equal(result.ok, false, JSON.stringify(children));
    if (!result.ok) {
      assert.equal(result.issues[0].code, 'structure');
      assert.equal(result.issues[0].element, 'a');
      assert.match(result.issues[0].message, /children.*arreglo.*strings/i);
    }
  }
});

test('children may be omitted, empty, or refer to existing elements', () => {
  for (const extra of [{}, { children: [] }]) {
    const result = validateCanvasSpec({ root: 'a', elements: { a: { type: 'Card', props: { title: 'x' }, ...extra } } });
    assert.equal(result.ok, true, JSON.stringify(result));
  }
  const result = validateCanvasSpec({ root: 'a', elements: {
    a: { type: 'Card', props: { title: 'x' }, children: ['b'] },
    b: { type: 'Text', props: { content: 'hola' } },
  } });
  assert.equal(result.ok, true, JSON.stringify(result));
});

test('input that is not a spec at all is rejected without throwing', () => {
  for (const junk of [null, 'x', 7, [], {}, { root: 1 }]) assert.equal(validateCanvasSpec(junk).ok, false);
});

test('the prompt lists every component so canvas_write can teach the model', () => {
  const prompt = canvasCatalogPrompt();
  for (const name of COMPONENT_NAMES) assert.match(prompt, new RegExp(name));
});

test('askAgent is a catalog action with its own params', () => {
  assert.equal(ACTION_NAMES.includes('askAgent'), true);
  const press = (action: string, params: unknown) => one('Button', { label: 'x', variant: null }, { on: { press: { action, params } } });
  assert.equal(validateCanvasSpec(press('askAgent', { message: 'explica esto' })).ok, true);
  assert.equal(validateCanvasSpec(press('askAgent', { message: '' })).ok, false);
});

test('canvasActionParams checks the params of askAgent and refuses a local, removed or unknown action', () => {
  assert.deepEqual(canvasActionParams('askAgent', { message: 'hola' }), { ok: true, action: 'askAgent', params: { message: 'hola' } });
  assert.equal(canvasActionParams('askAgent', { message: '' }).ok, false);
  assert.equal(canvasActionParams('callTool', { tool: 'x' }).ok, false);
  assert.equal(canvasActionParams('setState', {}).ok, false);
  assert.equal(canvasActionParams('nope', {}).ok, false);
});

test('form fields, local actions and askAgent make a working form', () => {
  const form = { root: 'f', state: { form: { name: '' } }, elements: {
    f: { type: 'Stack', props: {}, children: ['name', 'send'] },
    name: { type: 'TextField', props: { label: 'Nombre', value: { $bindState: '/form/name' } } },
    send: { type: 'Button', props: { label: 'Preguntar' }, on: { press: [
      { action: 'validateForm', params: {} },
      { action: 'askAgent', params: { message: { $template: 'Soy ${/form/name}' } } },
    ] } },
  } };
  assert.equal(validateCanvasSpec(form).ok, true, JSON.stringify(validateCanvasSpec(form)));
});
