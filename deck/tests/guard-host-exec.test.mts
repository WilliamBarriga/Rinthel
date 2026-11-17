import { after, test } from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import type { AddressInfo } from 'node:net';
import { mkdirSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { FakeDaemon } from './helpers/fake-daemon.mts';
import { fakeLlama } from './helpers/fake-llama.mts';
import { fakeHostexecd } from './helpers/fake-hostexecd.mts';

/**
 * Host exec in an admin's Session, at two seams. First the tools as pi sees them (what the inline
 * factory registers, and what its `execute` does against a fake hostexecd). Then end to end at Deck's
 * HTTP surface, composed as `index.ts` composes it: the real Session manager running pi's SDK, the
 * Guard and the Session taint, with the daemon, llama-server and hostexecd as fakes over real HTTP.
 * Nothing here runs a command on the host.
 */
const SECRET = 'host-exec-test-secret';
process.env.RINTHEL_PANEL_SECRET = SECRET;
const root = mkdtempSync(path.join(tmpdir(), 'deck-host-exec-'));
process.env.PI_CODING_AGENT_DIR = path.join(root, 'pi-agent');
mkdirSync(process.env.PI_CODING_AGENT_DIR, { recursive: true });

const { hostExecExtension, HOST_EXEC_TOOLS } = await import('../server/src/pi/host-exec/host-exec-tools.ts');
const { TAINT_REVOKED_TOOLS } = await import('../server/src/pi/guard.ts');
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

const hostexecd = await fakeHostexecd();
const access = { url: hostexecd.url, token: hostexecd.token };

// ── The tools as pi sees them ────────────────────────────────────────────────

function register(adminNow: () => Promise<boolean>, over: Partial<typeof access> = {}) {
  const tools = new Map<string, any>();
  hostExecExtension({ ...access, ...over, adminNow })({ registerTool: (tool: any) => void tools.set(tool.name, tool) } as any);
  return tools;
}

const text = (result: any) => result.content.map((c: any) => c.text).join('');

test('the factory registers exactly the two host exec tools, and the tainted Guard revokes both', () => {
  const tools = register(async () => true);
  assert.deepEqual([...tools.keys()].sort(), [...HOST_EXEC_TOOLS].sort());
  for (const name of HOST_EXEC_TOOLS) assert.ok(TAINT_REVOKED_TOOLS.has(name), name);
});

test('a call from an admin reaches hostexecd with the token, and its output comes back to the model', async () => {
  hostexecd.result = { exit_code: 3, stdout: 'GPU 0\n', stderr: 'warn\n', duration_ms: 12, timed_out: false };
  const before = hostexecd.execs.length;
  const out = await register(async () => true).get('rinthel_host_exec').execute('c1', { command: 'nvidia-smi -L', cwd: '/tmp', timeout: 5 });
  assert.deepEqual(hostexecd.execs.slice(before), [{ command: 'nvidia-smi -L', cwd: '/tmp', timeout: 5 }]);
  assert.match(text(out), /exit 3 \(12ms\)/);
  assert.match(text(out), /stdout:\nGPU 0/);
  assert.match(text(out), /stderr:\nwarn/);
  assert.deepEqual(out.details, { exit_code: 3, timed_out: false });
});

test('the history lists the audited runs, most recent first', async () => {
  hostexecd.history = [
    { ts: 1_700_000_100, command: 'uptime', cwd: null, exit_code: 0, duration_ms: 4, stdout_len: 10, stderr_len: 0, timed_out: false },
    { ts: 1_700_000_000, command: 'sleep 99', cwd: null, exit_code: -1, duration_ms: 60000, stdout_len: 0, stderr_len: 0, timed_out: true },
  ];
  const out = text(await register(async () => true).get('rinthel_host_exec_history').execute('c1', { limit: 5 }));
  const lines = out.split('\n');
  assert.match(lines[0], /exit 0 \(4ms\): uptime$/);
  assert.match(lines[1], /exit -1 TIMEOUT \(60000ms\): sleep 99$/);
});

test('the role is checked on every call: no longer an admin, or no answer about it, and nothing reaches the host', async () => {
  const before = hostexecd.requests.length;
  for (const adminNow of [async () => false, async () => { throw new Error('daemon down'); }]) {
    const tools = register(adminNow);
    for (const name of HOST_EXEC_TOOLS) {
      await assert.rejects(tools.get(name).execute('c1', { command: 'id' }), /admin/);
    }
  }
  assert.equal(hostexecd.requests.length, before);
});

test('a token hostexecd refuses, or a hostexecd that is down, is an error for the model, not a crash', async () => {
  const wrong = register(async () => true, { token: 'wrong' }).get('rinthel_host_exec');
  await assert.rejects(wrong.execute('c1', { command: 'id' }), /401/);
  const down = register(async () => true, { url: 'http://127.0.0.1:9' }).get('rinthel_host_exec');
  await assert.rejects(down.execute('c1', { command: 'id' }), /hostexecd/);
});

test('with a token, a URL that cannot be hostexecd fails the registration', () => {
  for (const url of ['', 'not a url', 'file:///etc/passwd']) {
    assert.throws(() => register(async () => true, { url }), /hostexecd/, url);
  }
});

// ── End to end at Deck's HTTP surface ────────────────────────────────────────

const llama = await fakeLlama(path.join(root, 'llama-slots'));
const daemon = new FakeDaemon(SECRET);
const ADMIN = daemon.addUser('root', 'root-password', 'admin');
const ANA = daemon.addUser('ana', 'ana-password');
daemon.models = [{ id: 'qwen-a', context_window: 65536 }];
daemon.activeModel = 'qwen-a';
daemon.llamaUrl = llama.url;
const identity = daemonSessionIdentity(daemon);
const routing = new DaemonModelRouting(daemon);

const closers: (() => Promise<void>)[] = [];
after(async () => {
  for (const close of closers.reverse()) await close();
  await llama.close();
  await hostexecd.close();
  rmSync(root, { recursive: true, force: true });
});

/** One Deck, composed as `index.ts` does, with `hostExec` as its environment would give it. */
async function deck(name: string, hostExec?: { url: string; token: string }) {
  const data = path.join(root, name);
  const store = createMemoryStore();
  const slots = new SessionSlots(new LlamaSlotStore(path.join(root, 'llama-slots')), { maxBytes: 1_000_000 });
  const roots = new FsSessionRoots(data, path.join(data, 'workspaces'));
  let sessions: InstanceType<typeof SessionManager>;
  const proxy = new SessionProxy({ routing, slots, onProgress: (id, p) => sessions.reportPrefill(id, p), onRoute: (id, r) => sessions.reportRoute(id, r) });
  await proxy.start();
  const canvases = createCanvases(store);
  const instanceSoul = new FsInstanceSoul(path.join(data, 'instance', 'SOUL.md'));
  sessions = new SessionManager({ store, identity, proxy, roots, canvases, instanceSoulFile: instanceSoul.path, hostExec, launch: (opts) => SdkPiClient.create(opts) });
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
  return { call, settled, adminSession };
}

const toolNames = (body: any): string[] => (body.tools ?? []).map((t: any) => t.function?.name);
const verdicts = (events: { type: string; payload: any }[]) =>
  events.filter((e) => e.type === 'portal_guard').map((e) => [e.payload.tool, e.payload.verdict]);

const withHostExec = await deck('with', access);

test('an admin runs a command on the host from a Session, and its output reaches the transcript', async () => {
  const id = await withHostExec.adminSession('host');
  hostexecd.result = { exit_code: 0, stdout: 'Linux\n', stderr: '', duration_ms: 2, timed_out: false };
  const before = hostexecd.execs.length;
  llama.toolCalls = [{ name: 'rinthel_host_exec', arguments: { command: 'uname -s' } }];
  const sent = await withHostExec.call('POST', `/api/sessions/${id}/prompt`, ADMIN, { message: 'qué sistema es' });
  assert.equal(sent.status, 200, JSON.stringify(sent.body));
  const events = await withHostExec.settled(id, ADMIN);

  assert.deepEqual(hostexecd.execs.slice(before).map((e) => e.command), ['uname -s']);
  assert.deepEqual(verdicts(events), [['rinthel_host_exec', 'allow']]);
  const result = events.find((e) => e.type === 'tool_execution_end' && e.payload.toolName === 'rinthel_host_exec');
  assert.ok(result, 'the tool ran');
  assert.equal(result!.payload.isError, false);
  assert.match(JSON.stringify(llama.bodies.at(-1).messages), /Linux/);
  for (const name of HOST_EXEC_TOOLS) assert.ok(toolNames(llama.bodies[llama.bodies.length - 2]).includes(name), name);
});

test("a member's Session never has the host exec tools", async () => {
  const id = (await withHostExec.call('POST', '/api/agent/sessions', ANA, {})).body.id;
  await withHostExec.call('POST', `/api/sessions/${id}/prompt`, ANA, { message: 'hola' });
  await withHostExec.settled(id, ANA);
  const names = toolNames(llama.bodies.at(-1));
  for (const name of HOST_EXEC_TOOLS) assert.ok(!names.includes(name), name);
});

test('a tainted Session loses host exec, and nothing reaches the host', async () => {
  const id = await withHostExec.adminSession('tainted');
  const before = hostexecd.execs.length;
  // `echo curl` reads nothing, but the Guard judges the command: its output counts as fetched.
  llama.toolCalls = [{ name: 'bash', arguments: { command: 'echo curl' } }, { name: 'rinthel_host_exec', arguments: { command: 'id' } }];
  await withHostExec.call('POST', `/api/sessions/${id}/prompt`, ADMIN, { message: 'lee y ejecuta' });
  const events = await withHostExec.settled(id, ADMIN);

  assert.deepEqual(verdicts(events), [['bash', 'allow'], ['rinthel_host_exec', 'deny']]);
  assert.equal(hostexecd.execs.length, before);
});

test('without a token an admin Session starts with no host exec tools, and nothing breaks', async () => {
  const without = await deck('without');
  const id = await without.adminSession('plain');
  const sent = await without.call('POST', `/api/sessions/${id}/prompt`, ADMIN, { message: 'hola' });
  assert.equal(sent.status, 200, JSON.stringify(sent.body));
  await without.settled(id, ADMIN);
  const names = toolNames(llama.bodies.at(-1));
  assert.ok(names.includes('bash'));
  for (const name of HOST_EXEC_TOOLS) assert.ok(!names.includes(name), name);
});

test('with a token, host exec that cannot register stops the admin Session from starting', async () => {
  const broken = await deck('broken', { url: 'not a url', token: 'tok' });
  const id = await broken.adminSession('broken');
  const completions = llama.bodies.length;
  const sent = await broken.call('POST', `/api/sessions/${id}/prompt`, ADMIN, { message: 'hola' });
  assert.ok(sent.status >= 400, JSON.stringify(sent.body));
  assert.equal(llama.bodies.length, completions);
  // A member's Session does not load host exec at all, so it still starts.
  const member = (await broken.call('POST', '/api/agent/sessions', ANA, {})).body.id;
  assert.equal((await broken.call('POST', `/api/sessions/${member}/prompt`, ANA, { message: 'hola' })).status, 200);
  await broken.settled(member, ANA);
});
