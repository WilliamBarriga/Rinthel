import { after, test } from 'node:test';
import assert from 'node:assert/strict';
import { once, EventEmitter } from 'node:events';
import type { AddressInfo } from 'node:net';
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { FakeDaemon } from './helpers/fake-daemon.mts';
import type { DeckSessions } from '../server/src/app.ts';
import { InMemorySessionRoots } from '../server/src/session-roots.ts';
import { InMemoryModelRouting } from '../server/src/model-routing/model-routing.ts';

/**
 * The trimmed Deck surfaces at the HTTP surface (`createDeckApp`) over the in-memory store and the
 * fake daemon: the Canvases of a Session and their one action («ask the agent»), the Instance SOUL
 * (a member reads it, an admin replaces it) and Appearance. No pi runs: the Sessions double records
 * whether anything asked for a Turn.
 */
const SECRET = 'surfaces-secret';
process.env.RINTHEL_PANEL_SECRET = SECRET;

const { createMemoryStore } = await import('../server/src/store/memory/index.ts');
const { createDeckApp } = await import('../server/src/app.ts');
const { ACCESS_COOKIE } = await import('../server/src/identity.ts');
const { daemonSessionIdentity } = await import('../server/src/daemon-session-identity.ts');
const { createCanvases } = await import('../server/src/canvases.ts');
const { createCanvasActions, storedSessionNotes } = await import('../server/src/canvas-actions.ts');
const { FsInstanceSoul } = await import('../server/src/instance-soul-fs.ts');

const root = mkdtempSync(path.join(tmpdir(), 'deck-surfaces-'));
const soulFile = path.join(root, 'instance', 'SOUL.md');
mkdirSync(path.dirname(soulFile), { recursive: true });
writeFileSync(soulFile, '# SOUL.md - seeded\n');

const store = createMemoryStore();
const daemon = new FakeDaemon(SECRET);
const ADMIN = daemon.addUser('root', 'root-password', 'admin');
const ANA = daemon.addUser('ana', 'ana-password');
const BEA = daemon.addUser('bea', 'bea-password');
const canvases = createCanvases(store);
const prompts: string[] = [];
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
    prompt: async (id: string) => void prompts.push(id),
  }) as unknown as DeckSessions,
  roots: new InMemorySessionRoots(),
  slots: { forget: async () => {} },
  routing: new InMemoryModelRouting(),
  canvases,
  canvasActions: createCanvasActions({ canvases, notes: storedSessionNotes(store) }),
  instanceSoul: new FsInstanceSoul(soulFile),
  webDist: path.join(root, 'no-web'),
});
const server = app.listen(0, '127.0.0.1');
await once(server, 'listening');
const base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
after(async () => {
  server.closeAllConnections();
  await new Promise<void>((r) => server.close(() => r()));
  rmSync(root, { recursive: true, force: true });
});

async function call(method: string, url: string, as: number, body?: unknown) {
  const res = await fetch(`${base}${url}`, {
    method,
    headers: { 'content-type': 'application/json', cookie: `${ACCESS_COOKIE}=${daemon.accessToken(as)}` },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  let json: any = text;
  try { json = JSON.parse(text); } catch { /* not JSON */ }
  return { status: res.status, body: json };
}

// --- Canvases ---

await store.sessions.create({ id: 'ana-chat', title: 'chat', workspace: '/w', executor: 'host', kind: 'agent', owner_user_id: ANA });

test('a ui canvas with a form: the person leaves a message for the Agent, which starts no Turn', async () => {
  const ui = await canvases.createCanvas('ana-chat', 'Formulario', 'ui');
  const sent = await call('POST', `/api/sessions/ana-chat/canvases/${ui.id}/actions`, ANA, { action: 'askAgent', params: { message: 'Quiero el informe de ventas' } });
  assert.deepEqual([sent.status, sent.body], [200, { ok: true }]);
  assert.deepEqual(prompts, []);
  // It waits for the next Turn, where the SessionManager hands it over.
  assert.deepEqual(await store.sessions.takeNotes('ana-chat'), ['Quiero el informe de ventas']);
});

test('canvas actions: only askAgent exists; a markdown canvas, an empty message and another Session are refused', async () => {
  const ui = await canvases.createCanvas('ana-chat', 'Otra', 'ui');
  const doc = await canvases.createCanvas('ana-chat', 'Notas', 'markdown');
  const act = (id: string, action: unknown, params: unknown, as = ANA) => call('POST', `/api/sessions/ana-chat/canvases/${id}/actions`, as, { action, params });
  assert.equal((await act(ui.id, 'callTool', { tool: 'x' })).status, 400);
  assert.equal((await act(ui.id, 'openDocument', { documentId: 'd' })).status, 400);
  assert.equal((await act(ui.id, 'askAgent', { message: '  ' })).status, 400);
  assert.equal((await act(doc.id, 'askAgent', { message: 'hola' })).status, 400);
  assert.equal((await act('ghost', 'askAgent', { message: 'hola' })).status, 404);
  assert.equal((await act(ui.id, 'askAgent', { message: 'hola' }, BEA)).status, 403);
  assert.deepEqual(await store.sessions.takeNotes('ana-chat'), []);
});

test('canvases of a Session: the owner and an admin list them, another member does not', async () => {
  const row = await canvases.createCanvas('ana-chat', 'Visible', 'markdown');
  const own = await call('GET', '/api/sessions/ana-chat/canvases', ANA);
  assert.equal(own.status, 200);
  assert.ok(own.body.some((c: any) => c.id === row.id));
  assert.equal((await call('GET', '/api/sessions/ana-chat/canvases', ADMIN)).status, 200);
  assert.equal((await call('GET', '/api/sessions/ana-chat/canvases', BEA)).status, 403);
  assert.equal((await call('GET', '/api/sessions/nope/canvases', ANA)).status, 404);
});

// --- Instance SOUL ---

test('a member reads the Instance SOUL and cannot edit it; an admin does and the member sees the change', async () => {
  const seen = await call('GET', '/api/agent/instance-soul', ANA);
  assert.deepEqual(seen.body, { name: 'SOUL.md', exists: true, content: '# SOUL.md - seeded\n', editable: false });
  assert.equal((await call('PUT', '/api/agent/instance-soul', ANA, { content: 'mine' })).status, 403);
  assert.equal((await call('GET', '/api/agent/instance-soul', ANA)).body.content, '# SOUL.md - seeded\n');

  const saved = await call('PUT', '/api/agent/instance-soul', ADMIN, { content: '# SOUL.md - edited' });
  assert.deepEqual([saved.status, saved.body.content, saved.body.editable], [200, '# SOUL.md - edited\n', true]);
  assert.equal((await call('GET', '/api/agent/instance-soul', ANA)).body.content, '# SOUL.md - edited\n');
  assert.equal((await call('GET', '/api/agent/instance-soul', ADMIN)).body.editable, true);
});

test('the Instance SOUL: a body without text and a page too long are refused', async () => {
  assert.equal((await call('PUT', '/api/agent/instance-soul', ADMIN, { content: 5 })).status, 400);
  assert.equal((await call('PUT', '/api/agent/instance-soul', ADMIN, { content: 'x'.repeat(20_001) })).status, 400);
});

test('the routes that left with the Legacy of the Agent and the SOUL history are not there', async () => {
  for (const [method, url] of [['GET', '/api/agent/legacy'], ['POST', '/api/agent/legacy/migrate'], ['GET', '/api/agent/instance-soul/history'], ['GET', '/api/audit/guard']] as const) {
    assert.equal((await call(method, url, ADMIN, method === 'POST' ? {} : undefined)).status, 404, url);
  }
});

// --- Appearance ---

test('appearance: a member saves their preferences and cannot touch the shared brand or colors', async () => {
  const config = { version: 1, preferences: { layout: 'operation', fontSize: 16 }, profiles: [] };
  assert.equal((await call('PUT', '/api/appearance', ANA, config)).status, 200);
  assert.equal((await call('GET', '/api/appearance', ANA)).body.personal.preferences.fontSize, 16);
  assert.equal((await call('GET', '/api/appearance', BEA)).body.personal, null);
  const brand = { version: 1, name: 'Mi Instance', tagline: '', accent: '#5046d8', secondary: '#54608c', navTone: 'neutral', logo: true, logoSize: 30, logoLight: '', logoDark: '' };
  assert.equal((await call('PUT', '/api/appearance/brand', ANA, brand)).status, 403);
  assert.equal((await call('PUT', '/api/appearance/brand', ADMIN, brand)).status, 200);
  assert.equal((await call('GET', '/api/appearance', BEA)).body.branding.name, 'Mi Instance');
  assert.equal((await call('PUT', '/api/appearance', ANA, { ...config, preferences: { theme: 'cyberpunk' } })).status, 403);
});
