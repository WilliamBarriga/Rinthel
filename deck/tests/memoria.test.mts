import { after, test } from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import type { AddressInfo } from 'node:net';
import { mkdirSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fakeUnderstory } from './helpers/fake-understory.mts';
import { FakeDaemon } from './helpers/fake-daemon.mts';
import { fakeLlama } from './helpers/fake-llama.mts';

/**
 * Memoria in an admin's Session, against a fake Understory over real HTTP (never the real one: it
 * holds the Instance's memory), at two seams. First the contract of the tools as pi sees them: what
 * the inline factory registers and what its `execute` sends and gets back. Then end to end at Deck's
 * HTTP surface, composed as `index.ts` composes it: the real Session manager running pi's SDK, the
 * Guard and the Session taint, with the daemon, llama-server and Understory as fakes.
 */
const SECRET = 'memoria-test-secret';
process.env.RINTHEL_PANEL_SECRET = SECRET;
const root = mkdtempSync(path.join(tmpdir(), 'deck-memoria-'));
process.env.PI_CODING_AGENT_DIR = path.join(root, 'pi-agent');
mkdirSync(process.env.PI_CODING_AGENT_DIR, { recursive: true });

const { memoriaExtension, MEMORIA_TOOLS, MEMORIA_CHILD_TOOLS, MEMORIA_TIMEOUT_MS } = await import('../server/src/pi/memoria/memoria-tools.ts');
const { CHILD_EXCLUDED_TOOLS } = await import('../server/src/pi/subagents/child.ts');
const { TAINT_REVOKED_TOOLS } = await import('../server/src/pi/guard.ts');

const understory = await fakeUnderstory();
const llama = await fakeLlama(path.join(root, 'llama-slots'));
const closers: (() => Promise<void>)[] = [];
after(async () => {
  for (const close of closers.reverse()) await close();
  await llama.close();
  await understory.close();
  rmSync(root, { recursive: true, force: true });
});

function register(opts: { adminNow?: () => Promise<boolean>; url?: () => Promise<string | null>; token?: string; timeoutMs?: number } = {}, tools?: readonly string[]) {
  const registered = new Map<string, any>();
  memoriaExtension({
    token: opts.token ?? understory.token,
    url: opts.url ?? (async () => understory.url),
    adminNow: opts.adminNow ?? (async () => true),
    timeoutMs: opts.timeoutMs,
  }, tools)({ registerTool: (tool: any) => void registered.set(tool.name, tool) } as any);
  return registered;
}

const text = (result: any) => result.content.map((c: any) => c.text).join('');

test('the factory registers the three Memoria tools, and no status nor maintain', () => {
  assert.deepEqual([...register().keys()].sort(), ['understory_memory_add', 'understory_memory_query', 'understory_memory_update']);
  assert.deepEqual([...MEMORIA_TOOLS].sort(), ['understory_memory_add', 'understory_memory_query', 'understory_memory_update']);
});

test("a query reaches Understory's memory_query with the token, and its answer comes back to the model", async () => {
  const before = understory.calls.length;
  const out = await register().get('understory_memory_query').execute('c1', { question: 'qué sistema corre' });
  assert.deepEqual(understory.calls.slice(before), [{ tool: 'memory_query', arguments: { question: 'qué sistema corre' } }]);
  assert.match(text(out), /runs on Linux/);
});

test('add and update reach their Understory tools with what the Agent wrote', async () => {
  const tools = register();
  const before = understory.calls.length;
  const added = await tools.get('understory_memory_add').execute('c1', { content: 'El host corre Linux.', suggested_path: '/reference/host.md' });
  const updated = await tools.get('understory_memory_update').execute('c2', { instruction: 'El host corre Linux 7.' });
  assert.deepEqual(understory.calls.slice(before), [
    { tool: 'memory_add', arguments: { content: 'El host corre Linux.', suggested_path: '/reference/host.md' } },
    { tool: 'memory_update', arguments: { instruction: 'El host corre Linux 7.' } },
  ]);
  assert.match(text(added), /Recorded/);
  assert.match(text(updated), /Updated/);
});

test('the role is checked on every call: no longer an admin, or no answer about it, and nothing reaches Understory', async () => {
  const before = understory.requests.length;
  for (const adminNow of [async () => false, async () => { throw new Error('daemon down'); }]) {
    const tools = register({ adminNow });
    await assert.rejects(tools.get('understory_memory_query').execute('c1', { question: 'q' }), /admin/);
    await assert.rejects(tools.get('understory_memory_add').execute('c1', { content: 'x' }), /admin/);
    await assert.rejects(tools.get('understory_memory_update').execute('c1', { instruction: 'x' }), /admin/);
  }
  assert.equal(understory.requests.length, before);
});

test('Understory down, off, unreadable or refusing the token is an error for the Agent, not a crash', async () => {
  const query = (opts: Parameters<typeof register>[0]) => register(opts).get('understory_memory_query').execute('c1', { question: 'q' });
  await assert.rejects(query({ url: async () => 'http://127.0.0.1:9' }), /Could not reach Understory/);
  await assert.rejects(query({ url: async () => null }), /Understory is off/);
  await assert.rejects(query({ url: async () => { throw new Error('routing unavailable'); } }), /could not be read/);
  await assert.rejects(query({ token: 'wrong' }), /401/);
});

test('a write Understory could not make is an error for the Agent', async () => {
  const saved = understory.answers.memory_add;
  delete understory.answers.memory_add;
  try {
    await assert.rejects(register().get('understory_memory_add').execute('c1', { content: 'x' }), /Mutation failed/);
  } finally {
    understory.answers.memory_add = saved;
  }
});

test('a call that outlasts the timeout is dropped with an error', async () => {
  understory.delayMs = 300;
  try {
    await assert.rejects(register({ timeoutMs: 50 }).get('understory_memory_query').execute('c1', { question: 'q' }), /did not answer within/);
  } finally {
    understory.delayMs = 0;
  }
});

test('the timeout is 40 minutes', () => {
  assert.equal(MEMORIA_TIMEOUT_MS, 40 * 60 * 1000);
});

test("a subagent's child gets the query alone, and never a Memoria write", () => {
  assert.deepEqual([...register({}, MEMORIA_CHILD_TOOLS).keys()], ['understory_memory_query']);
  for (const name of ['understory_memory_add', 'understory_memory_update', 'understory_memory_maintain']) assert.ok(CHILD_EXCLUDED_TOOLS.includes(name), name);
  assert.ok(!CHILD_EXCLUDED_TOOLS.includes('understory_memory_query'));
});

test('the tainted Guard revokes both writes, and reading is not an untrusted source', () => {
  assert.ok(TAINT_REVOKED_TOOLS.has('understory_memory_add'));
  assert.ok(TAINT_REVOKED_TOOLS.has('understory_memory_update'));
  assert.ok(!TAINT_REVOKED_TOOLS.has('understory_memory_query'));
});

// ── End to end at Deck's HTTP surface ────────────────────────────────────────

const { createMemoryStore } = await import('../server/src/store/memory/index.ts');
const { createDeckApp } = await import('../server/src/app.ts');
const { ACCESS_COOKIE } = await import('../server/src/identity.ts');
const { daemonSessionIdentity } = await import('../server/src/daemon-session-identity.ts');
const { DaemonModelRouting } = await import('../server/src/model-routing/daemon-model-routing.ts');
const { SessionSlots } = await import('../server/src/session-slots/session-slots.ts');
const { LlamaSlotStore } = await import('../server/src/session-slots/llama-slot-store.ts');
const { SessionProxy } = await import('../server/src/session-proxy.ts');
const { SessionManager } = await import('../server/src/session-manager.ts');
const { SdkPiClient } = await import('../server/src/pi/sdk-client.ts');
const { FsSessionRoots } = await import('../server/src/session-roots-fs.ts');
const { createCanvases } = await import('../server/src/canvases.ts');
const { createCanvasActions, storedSessionNotes } = await import('../server/src/canvas-actions.ts');
const { FsInstanceSoul } = await import('../server/src/instance-soul-fs.ts');

const daemon = new FakeDaemon(SECRET);
const ADMIN = daemon.addUser('root', 'root-password', 'admin');
const ANA = daemon.addUser('ana', 'ana-password');
daemon.models = [{ id: 'qwen-a', context_window: 65536 }];
daemon.activeModel = 'qwen-a';
daemon.llamaUrl = llama.url;
daemon.understoryUrl = understory.url;
const identity = daemonSessionIdentity(daemon);
const routing = new DaemonModelRouting(daemon);

/** One Deck, composed as `index.ts` does, with `UNDERSTORY_TOKEN` as its environment would give it. */
async function deck(name: string, understoryToken?: string) {
  const data = path.join(root, name);
  const store = createMemoryStore();
  const slots = new SessionSlots(new LlamaSlotStore(path.join(root, 'llama-slots')), { maxBytes: 1_000_000 });
  const roots = new FsSessionRoots(data, path.join(data, 'workspaces'));
  let sessions: InstanceType<typeof SessionManager>;
  const proxy = new SessionProxy({ routing, slots, onProgress: (id, p) => sessions.reportPrefill(id, p), onRoute: (id, r) => sessions.reportRoute(id, r) });
  await proxy.start();
  const canvases = createCanvases(store);
  const instanceSoul = new FsInstanceSoul(path.join(data, 'instance', 'SOUL.md'));
  const memoria = understoryToken ? { token: understoryToken, url: () => routing.understoryUrl() } : undefined;
  sessions = new SessionManager({ store, identity, proxy, roots, canvases, instanceSoulFile: instanceSoul.path, memoria, launch: (opts) => SdkPiClient.create(opts) });
  const app = createDeckApp({ store, daemon, identity, serviceSecret: 'svc', sessions, roots, slots, routing, canvases, canvasActions: createCanvasActions({ canvases, notes: storedSessionNotes(store) }), instanceSoul, webDist: path.join(root, 'no-web') });
  const server = app.listen(0, '127.0.0.1');
  await once(server, 'listening');
  closers.push(async () => {
    await sessions.shutdown();
    proxy.stop();
    server.closeAllConnections();
    await new Promise<void>((r) => server.close(() => r()));
  });
  const base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  async function call(method: string, url: string, as: number, body?: unknown) {
    const res = await fetch(`${base}${url}`, {
      method,
      headers: { 'content-type': 'application/json', cookie: `${ACCESS_COOKIE}=${daemon.accessToken(as)}` },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const raw = await res.text();
    let json: any = raw;
    try { json = JSON.parse(raw); } catch { /* not JSON */ }
    return { status: res.status, body: json };
  }
  async function settled(id: string, as: number) {
    for (let i = 0; i < 200; i++) {
      const s = await call('GET', `/api/sessions/${id}`, as);
      if (s.body.status === 'idle' || s.body.status === 'error') break;
      await new Promise((r) => setTimeout(r, 25));
    }
    await slots.idle();
    return (await call('GET', `/api/sessions/${id}/events/before?before=999999999`, as)).body.events as { type: string; payload: any }[];
  }
  /** A new admin task Session on its own workspace. */
  async function adminSession(workspace: string) {
    await call('POST', '/api/workspaces', ADMIN, { name: workspace });
    return (await call('POST', '/api/sessions', ADMIN, { workspace })).body.id as string;
  }
  async function prompt(id: string, as: number, message: string) {
    const sent = await call('POST', `/api/sessions/${id}/prompt`, as, { message });
    assert.equal(sent.status, 200, JSON.stringify(sent.body));
    return settled(id, as);
  }
  return { call, settled, adminSession, prompt };
}

const toolNames = (body: any): string[] => (body.tools ?? []).map((t: any) => t.function?.name);
const verdicts = (events: { type: string; payload: any }[]) =>
  events.filter((e) => e.type === 'portal_guard').map((e) => [e.payload.tool, e.payload.verdict]);
const toolEnd = (events: { type: string; payload: any }[], name: string) =>
  events.filter((e) => e.type === 'tool_execution_end' && e.payload.toolName === name);

const withMemoria = await deck('with', understory.token);

test('an admin asks and writes the Memoria from a Session; reading does not taint it, so the write goes through', async () => {
  const id = await withMemoria.adminSession('memoria');
  const before = understory.calls.length;
  const first = llama.bodies.length;
  llama.toolCalls = [
    { name: 'understory_memory_query', arguments: { question: 'qué sistema corre' } },
    { name: 'understory_memory_add', arguments: { content: 'El host corre Linux.' } },
  ];
  const events = await withMemoria.prompt(id, ADMIN, 'recordá esto');

  assert.deepEqual(understory.calls.slice(before), [
    { tool: 'memory_query', arguments: { question: 'qué sistema corre' } },
    { tool: 'memory_add', arguments: { content: 'El host corre Linux.' } },
  ]);
  assert.deepEqual(verdicts(events), [['understory_memory_query', 'allow'], ['understory_memory_add', 'allow']]);
  for (const name of ['understory_memory_query', 'understory_memory_add']) assert.equal(toolEnd(events, name)[0]?.payload.isError, false, name);
  // The answer reaches the model as it is, not inside an untrusted envelope.
  const answered = JSON.stringify(llama.bodies.at(-1).messages);
  assert.match(answered, /runs on Linux/);
  assert.doesNotMatch(answered, /<<<untrusted:/);
  for (const name of MEMORIA_TOOLS) assert.ok(toolNames(llama.bodies[first]).includes(name), name);
});

test("a member's Session never has the Memoria tools", async () => {
  const id = (await withMemoria.call('POST', '/api/agent/sessions', ANA, {})).body.id;
  await withMemoria.prompt(id, ANA, 'hola');
  const names = toolNames(llama.bodies.at(-1));
  for (const name of ['understory_memory_query', 'understory_memory_add', 'understory_memory_update']) assert.ok(!names.includes(name), name);
});

test('a tainted Session still reads the Memoria but loses its writes, and nothing is written', async () => {
  const id = await withMemoria.adminSession('tainted');
  const before = understory.calls.length;
  // `echo curl` reads nothing, but the Guard judges the command: its output counts as fetched.
  llama.toolCalls = [
    { name: 'bash', arguments: { command: 'echo curl' } },
    { name: 'understory_memory_add', arguments: { content: 'x' } },
    { name: 'understory_memory_update', arguments: { instruction: 'x' } },
    { name: 'understory_memory_query', arguments: { question: 'q' } },
  ];
  const events = await withMemoria.prompt(id, ADMIN, 'lee y escribe');

  assert.deepEqual(verdicts(events), [
    ['bash', 'allow'], ['understory_memory_add', 'deny'], ['understory_memory_update', 'deny'], ['understory_memory_query', 'allow'],
  ]);
  assert.deepEqual(understory.calls.slice(before).map((c) => c.tool), ['memory_query']);
});

test("a subagent's child reads the Memoria and never gets its writes", async () => {
  const id = await withMemoria.adminSession('child');
  const first = llama.bodies.length;
  llama.toolCalls = [{ name: 'subagent', arguments: { agent: 'scout', task: 'look' } }, null, null];
  await withMemoria.prompt(id, ADMIN, 'delegá');

  const [parent, child] = llama.bodies.slice(first);
  assert.ok(toolNames(parent).includes('understory_memory_add'));
  const names = toolNames(child);
  assert.ok(names.includes('understory_memory_query'), names.join(','));
  for (const name of ['understory_memory_add', 'understory_memory_update']) assert.ok(!names.includes(name), name);
});

test('Understory down: the tool is an error for the Agent, and the Session goes on', async () => {
  const id = await withMemoria.adminSession('down');
  daemon.understoryUrl = 'http://127.0.0.1:9';
  try {
    llama.toolCalls = [{ name: 'understory_memory_query', arguments: { question: 'q' } }];
    const events = await withMemoria.prompt(id, ADMIN, 'consultá');
    const [end] = toolEnd(events, 'understory_memory_query');
    assert.equal(end?.payload.isError, true);
    assert.match(JSON.stringify(end.payload.result), /Could not reach Understory/);
    // The Session still answers the next prompt.
    const turns = llama.bodies.length;
    await withMemoria.prompt(id, ADMIN, 'seguí');
    assert.ok(llama.bodies.length > turns);
  } finally {
    daemon.understoryUrl = understory.url;
  }
});

test('Understory off or the daemon not saying where it is never stops an admin Session from starting', async () => {
  daemon.understoryUrl = null;
  try {
    const id = await withMemoria.adminSession('off');
    llama.toolCalls = [{ name: 'understory_memory_query', arguments: { question: 'q' } }];
    const events = await withMemoria.prompt(id, ADMIN, 'consultá');
    assert.match(JSON.stringify(toolEnd(events, 'understory_memory_query')[0]?.payload.result), /Understory is off/);
  } finally {
    daemon.understoryUrl = understory.url;
  }
});

test('without UNDERSTORY_TOKEN an admin Session starts with no Memoria tools', async () => {
  const without = await deck('without');
  const id = await without.adminSession('plain');
  await without.prompt(id, ADMIN, 'hola');
  const names = toolNames(llama.bodies.at(-1));
  assert.ok(names.includes('bash'));
  for (const name of MEMORIA_TOOLS) assert.ok(!names.includes(name), name);
});
