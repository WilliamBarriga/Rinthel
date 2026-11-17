import { after, test } from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import type { AddressInfo } from 'node:net';
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { FakeDaemon } from './helpers/fake-daemon.mts';
import { fakeLlama } from './helpers/fake-llama.mts';
import { fakeHostexecd } from './helpers/fake-hostexecd.mts';

/**
 * The `subagent` tool of an admin's Session, at two seams. First the tool as pi sees it (what the
 * inline factory registers and logs, and its role check). Then end to end at Deck's HTTP surface,
 * composed as `index.ts` composes it: the real Session manager running pi's SDK for the parent and
 * its child, the Guard and the Session taint, with the daemon, llama-server and hostexecd as fakes.
 */
const SECRET = 'subagents-test-secret';
process.env.RINTHEL_PANEL_SECRET = SECRET;
const root = mkdtempSync(path.join(tmpdir(), 'deck-subagents-'));
const agentDir = path.join(root, 'pi-agent');
process.env.PI_CODING_AGENT_DIR = agentDir;
// The volume's own `scout` replaces the image's: its prompt is how the child is recognised below.
const VOLUME_MARK = 'VOLUME-SCOUT-7f3a';
mkdirSync(path.join(agentDir, 'agents'), { recursive: true });
writeFileSync(
  path.join(agentDir, 'agents', 'scout.md'),
  `---\nname: scout\ndescription: The volume's scout\ntools: read, ls, bash\n---\n\n${VOLUME_MARK}: map the code and report.\n`,
);

const { subagentExtension, SUBAGENT_TOOL } = await import('../server/src/pi/subagents/subagent-tool.ts');
const { TAINT_REVOKED_TOOLS } = await import('../server/src/pi/guard.ts');
const { SUBAGENT_TOOLS } = await import('../server/src/pi/session-taint.ts');
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

// ── The tool as pi sees it ───────────────────────────────────────────────────

const noModel = { url: 'http://127.0.0.1:9', route: () => null };

async function register(adminNow: () => Promise<boolean>, log: (line: string) => void = () => {}) {
  const tools = new Map<string, any>();
  await subagentExtension({ sessionId: 's1', agentDir, modelAccess: noModel, adminNow, childTools: [], log })({
    registerTool: (tool: any) => void tools.set(tool.name, tool),
  } as any);
  return tools;
}

test('the factory registers the subagent tool, which a tainted Session loses and whose answer taints it', async () => {
  const tools = await register(async () => true);
  assert.deepEqual([...tools.keys()], [SUBAGENT_TOOL]);
  assert.ok(TAINT_REVOKED_TOOLS.has(SUBAGENT_TOOL));
  assert.ok(SUBAGENT_TOOLS.has(SUBAGENT_TOOL));
});

test("the image's agents and the volume's are offered together, the volume's winning its name, and the override is logged", async () => {
  const lines: string[] = [];
  const description = (await register(async () => true, (line) => lines.push(line))).get(SUBAGENT_TOOL).description as string;
  for (const name of ['worker', 'reviewer', 'planner', 'researcher', 'debugger', 'builder', 'writer', 'custom']) {
    assert.match(description, new RegExp(`\\b${name}:`), name);
  }
  assert.match(description, /scout: The volume's scout/);
  assert.equal(lines.filter((l) => /scout/.test(l)).length, 1, lines.join('\n'));
  assert.match(lines.find((l) => /scout/.test(l))!, new RegExp(path.join(agentDir, 'agents', 'scout.md').replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
});

test('the role is checked on every call: no longer an admin, or no answer about it, and no child runs', async () => {
  for (const adminNow of [async () => false, async () => { throw new Error('daemon down'); }]) {
    const tool = (await register(adminNow)).get(SUBAGENT_TOOL);
    await assert.rejects(tool.execute('c1', { agent: 'scout', task: 'look' }, undefined, undefined, { cwd: root }), /admin/);
  }
});

// ── End to end at Deck's HTTP surface ────────────────────────────────────────

const llama = await fakeLlama(path.join(root, 'llama-slots'));
const hostexecd = await fakeHostexecd();
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

/** One Deck, composed as `index.ts` does, with host exec on so the child can be seen without it. */
async function deck() {
  const data = path.join(root, 'deck');
  const store = createMemoryStore();
  const slots = new SessionSlots(new LlamaSlotStore(path.join(root, 'llama-slots')), { maxBytes: 1_000_000 });
  const roots = new FsSessionRoots(data, path.join(data, 'workspaces'));
  let sessions: InstanceType<typeof SessionManager>;
  const proxy = new SessionProxy({ routing, slots, onProgress: (id, p) => sessions.reportPrefill(id, p), onRoute: (id, r) => sessions.reportRoute(id, r) });
  await proxy.start();
  const canvases = createCanvases(store);
  const instanceSoul = new FsInstanceSoul(path.join(data, 'instance', 'SOUL.md'));
  sessions = new SessionManager({
    store, identity, proxy, roots, canvases, instanceSoulFile: instanceSoul.path,
    hostExec: { url: hostexecd.url, token: hostexecd.token },
    launch: (opts) => SdkPiClient.create(opts),
  });
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
    for (let i = 0; i < 400; i++) {
      const s = await call('GET', `/api/sessions/${id}`, as);
      if (s.body.status === 'idle' || s.body.status === 'error') break;
      await new Promise((r) => setTimeout(r, 25));
    }
    await slots.idle();
    return (await call('GET', `/api/sessions/${id}/events/before?before=999999999`, as)).body.events as { type: string; payload: any }[];
  }
  async function adminSession(workspace: string) {
    await call('POST', '/api/workspaces', ADMIN, { name: workspace });
    return (await call('POST', '/api/sessions', ADMIN, { workspace })).body.id as string;
  }
  return { call, settled, adminSession };
}

const toolNames = (body: any): string[] => (body.tools ?? []).map((t: any) => t.function?.name);
const systemOf = (body: any): string => JSON.stringify((body.messages ?? []).filter((m: any) => m.role === 'system'));
const verdicts = (events: { type: string; payload: any }[]) =>
  events.filter((e) => e.type === 'portal_guard').map((e) => [e.payload.tool, e.payload.verdict]);

const instance = await deck();

test('an admin delegates to a child on the same model, gets its answer as untrusted, and the Session is tainted', async () => {
  const id = await instance.adminSession('delegate');
  const first = llama.bodies.length;
  const log = llama.log.length;
  llama.answer = ['child', '-finding'];
  // Parent asks for the child; the child answers; the parent, now tainted, asks again; then answers.
  llama.toolCalls = [
    { name: 'subagent', arguments: { agent: 'scout', task: 'map the repo' } },
    null,
    { name: 'subagent', arguments: { agent: 'scout', task: 'again' } },
    null,
  ];
  const sent = await instance.call('POST', `/api/sessions/${id}/prompt`, ADMIN, { message: 'delegá' });
  assert.equal(sent.status, 200, JSON.stringify(sent.body));
  const events = await instance.settled(id, ADMIN);

  const bodies = llama.bodies.slice(first);
  assert.equal(bodies.length, 4, bodies.map(systemOf).join('\n'));
  const [parent, child, parentAfter] = bodies;
  // The child: the volume's scout, the parent's model, its agent's tools and never what a tainted Session loses.
  assert.ok(systemOf(child).includes(VOLUME_MARK));
  assert.ok(!systemOf(parent).includes(VOLUME_MARK));
  assert.equal(child.model, parent.model);
  assert.deepEqual(toolNames(child).sort(), ['bash', 'ls', 'read']);
  assert.ok(toolNames(parent).includes('subagent'));
  assert.ok(toolNames(parent).includes('rinthel_host_exec'));
  // Its answer reaches the parent inside the Guard's envelope.
  const answered = JSON.stringify(parentAfter.messages);
  assert.match(answered, /child-finding/);
  assert.match(answered, /<<<untrusted:[0-9a-f]+>>>/);
  // The second call is refused: the Session is tainted.
  assert.deepEqual(verdicts(events), [['subagent', 'allow'], ['subagent', 'deny']]);
  // Parent and child take the Session's slot one request at a time: restore, call, save, four times over.
  const slotLog = llama.log.slice(log);
  assert.equal(slotLog.length, 12, slotLog.join('\n'));
  const slot = slotLog[0].split(' ')[1];
  for (let i = 0; i < 4; i++) {
    assert.deepEqual(slotLog.slice(i * 3, i * 3 + 3), [`restore ${slot}`, 'completion qwen-a', `save ${slot}`]);
  }
});

test("a member's Session never has the subagent tool", async () => {
  const id = (await instance.call('POST', '/api/agent/sessions', ANA, {})).body.id;
  await instance.call('POST', `/api/sessions/${id}/prompt`, ANA, { message: 'hola' });
  await instance.settled(id, ANA);
  assert.ok(!toolNames(llama.bodies.at(-1)).includes('subagent'));
});

test('a Session tainted before the call never starts a child', async () => {
  const id = await instance.adminSession('tainted');
  const first = llama.bodies.length;
  llama.toolCalls = [{ name: 'bash', arguments: { command: 'echo curl' } }, { name: 'subagent', arguments: { agent: 'scout', task: 'look' } }, null];
  await instance.call('POST', `/api/sessions/${id}/prompt`, ADMIN, { message: 'lee y delegá' });
  const events = await instance.settled(id, ADMIN);
  assert.deepEqual(verdicts(events), [['bash', 'allow'], ['subagent', 'deny']]);
  assert.ok(!llama.bodies.slice(first).some((b) => systemOf(b).includes(VOLUME_MARK)));
});
