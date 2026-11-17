import { after, test } from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import type { AddressInfo } from 'node:net';
import { existsSync, mkdirSync, mkdtempSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { FakeDaemon } from './helpers/fake-daemon.mts';
import { fakeLlama } from './helpers/fake-llama.mts';

/**
 * The chat end to end at Deck's HTTP surface (`createDeckApp`), composed as `index.ts` composes it:
 * the real Session manager running pi's SDK in this process, the real proxy and slot store, and the
 * daemon's route read over the daemon client. Only the daemon and llama-server are fakes (llama over
 * real HTTP, its slots on a temporary `--slot-save-path`).
 */
const SECRET = 'chat-test-secret';
process.env.RINTHEL_PANEL_SECRET = SECRET;
const root = mkdtempSync(path.join(tmpdir(), 'deck-chat-'));
// pi's own directory: nothing of the host's pi is read.
process.env.PI_CODING_AGENT_DIR = path.join(root, 'pi-agent');
mkdirSync(process.env.PI_CODING_AGENT_DIR, { recursive: true });

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
const { MEMBER_TOOLS } = await import('../server/src/tool-profile.ts');
const { FsInstanceSoul } = await import('../server/src/instance-soul-fs.ts');

const slotsDir = path.join(root, 'data', 'llama-slots');
const llama = await fakeLlama(slotsDir);
const daemon = new FakeDaemon(SECRET);
const ADMIN = daemon.addUser('root', 'root-password', 'admin');
const ANA = daemon.addUser('ana', 'ana-password');
const BEA = daemon.addUser('bea', 'bea-password');
daemon.models = [{ id: 'qwen-a', context_window: 65536 }, { id: 'qwen-b', context_window: 131072 }];
daemon.activeModel = 'qwen-a';
daemon.llamaUrl = llama.url;

const store = createMemoryStore();
const identity = daemonSessionIdentity(daemon);
const routing = new DaemonModelRouting(daemon);
const slots = new SessionSlots(new LlamaSlotStore(slotsDir), { maxBytes: 1_000_000 });
const roots = new FsSessionRoots(path.join(root, 'data'), path.join(root, 'data', 'workspaces'));
let sessions: InstanceType<typeof SessionManager>;
const proxy = new SessionProxy({
  routing, slots,
  onProgress: (id, prefill) => sessions.reportPrefill(id, prefill),
  onRoute: (id, route) => sessions.reportRoute(id, route),
});
await proxy.start();
const canvases = createCanvases(store);
const instanceSoul = new FsInstanceSoul(path.join(root, 'data', 'instance', 'SOUL.md'));
sessions = new SessionManager({ store, identity, proxy, roots, canvases, instanceSoulFile: instanceSoul.path, launch: (opts) => SdkPiClient.create(opts) });
const app = createDeckApp({ store, daemon, identity, serviceSecret: 'svc', sessions, roots, slots, routing, canvases, canvasActions: createCanvasActions({ canvases, notes: storedSessionNotes(store) }), instanceSoul, webDist: path.join(root, 'no-web') });
const server = app.listen(0, '127.0.0.1');
await once(server, 'listening');
const base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
after(async () => {
  await sessions.shutdown();
  proxy.stop();
  server.closeAllConnections();
  await new Promise<void>((r) => server.close(() => r()));
  await llama.close();
  rmSync(root, { recursive: true, force: true });
});

const cookie = (id: number) => `${ACCESS_COOKIE}=${daemon.accessToken(id)}`;
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

/** Polls until the Session is idle again after a prompt, then returns its stored events. */
async function settled(id: string, as: number) {
  for (let i = 0; i < 200; i++) {
    const s = await call('GET', `/api/sessions/${id}`, as);
    if (s.body.status === 'idle' || s.body.status === 'error') break;
    await new Promise((r) => setTimeout(r, 25));
  }
  await slots.idle();
  return (await call('GET', `/api/sessions/${id}/events/before?before=999999999`, as)).body.events as { type: string; payload: any }[];
}

const assistantText = (events: { type: string; payload: any }[]) => events
  .filter((e) => e.type === 'message_end' && e.payload.message?.role === 'assistant')
  .map((e) => e.payload.message.content.filter((c: any) => c.type === 'text').map((c: any) => c.text).join(''));

const promptText = (body: any) => JSON.stringify(body.messages);

test('a member chats in an agent Session: the turn goes to the Local model and its answer reaches the transcript', async () => {
  const created = await call('POST', '/api/agent/sessions', ANA, {});
  assert.equal(created.status, 200);
  assert.equal(created.body.kind, 'agent');
  const id = created.body.id;
  const sent = await call('POST', `/api/sessions/${id}/prompt`, ANA, { message: 'hola' });
  assert.equal(sent.status, 200, JSON.stringify(sent.body));
  const events = await settled(id, ANA);
  assert.deepEqual(events.filter((e) => e.type === 'portal_prompt').map((e) => e.payload.message), ['hola']);
  assert.deepEqual(assistantText(events), ['hola']);
  const body = llama.bodies.at(-1);
  assert.equal(body.model, 'qwen-a');
  // A member's closed profile: only the canvas tools reach the model.
  assert.deepEqual(body.tools.map((t: any) => t.function.name).sort(), [...MEMBER_TOOLS].sort());
});

test('a member\'s Session loads the Instance SOUL as its own, and never a SOUL.md of their home', async () => {
  instanceSoul.write('# SOUL.md\nYou are Aria, the Agent of this Instance.');
  const id = (await call('POST', '/api/agent/sessions', ANA, {})).body.id;
  const home = roots.agentHome(ANA);
  mkdirSync(home, { recursive: true });
  writeFileSync(path.join(home, 'SOUL.md'), 'You are their own private SOUL.\n');
  await call('POST', `/api/sessions/${id}/prompt`, ANA, { message: 'quien eres' });
  await settled(id, ANA);
  const sent = promptText(llama.bodies.at(-1));
  assert.match(sent, /You are Aria, the Agent of this Instance/);
  assert.doesNotMatch(sent, /private SOUL/);
});

test('the staff framing (name and role) goes to the model in the first prompt of a Session, and only the first', async () => {
  const id = (await call('POST', '/api/agent/sessions', ANA, {})).body.id;
  await call('POST', `/api/sessions/${id}/prompt`, ANA, { message: 'primero' });
  await settled(id, ANA);
  assert.match(promptText(llama.bodies.at(-1)), /staff-framing[^]*ana \(miembro\)/);
  await call('POST', `/api/sessions/${id}/prompt`, ANA, { message: 'segundo' });
  const events = await settled(id, ANA);
  const last = promptText(llama.bodies.at(-1));
  assert.equal(last.match(/staff-framing>/g)?.length, 2, 'the opening and closing tag of the first prompt, once');
  assert.ok(!JSON.stringify(events.filter((e) => e.type === 'portal_prompt')).includes('staff-framing'), 'the transcript shows what the person wrote');
});

test('an admin writing in a member\'s Session supervises: the framing says the Session acts for its owner', async () => {
  const id = (await call('POST', '/api/agent/sessions', ANA, {})).body.id;
  await call('POST', `/api/sessions/${id}/prompt`, ADMIN, { message: 'reviso' });
  await settled(id, ADMIN);
  assert.match(promptText(llama.bodies.at(-1)), /administrador supervisa/);
});

test('an admin chats in a task Session on a workspace, with the general Agent and its tools', async () => {
  const ws = await call('POST', '/api/workspaces', ADMIN, { name: 'Proyecto Uno' });
  assert.equal(ws.body.name, 'proyecto-uno');
  const created = await call('POST', '/api/sessions', ADMIN, { workspace: 'proyecto-uno' });
  assert.equal(created.status, 200, JSON.stringify(created.body));
  await call('POST', `/api/sessions/${created.body.id}/prompt`, ADMIN, { message: 'lista archivos' });
  const events = await settled(created.body.id, ADMIN);
  assert.deepEqual(assistantText(events), ['hola']);
  assert.ok(llama.bodies.at(-1).tools.some((t: any) => t.function?.name === 'bash'));
  // A member does not see the admin's workspaces nor Sessions.
  assert.deepEqual((await call('GET', '/api/workspaces', BEA)).body.workspaces, []);
  assert.equal((await call('GET', `/api/sessions/${created.body.id}`, BEA)).status, 403);
  assert.ok(!(await call('GET', '/api/sessions', BEA)).body.sessions.some((s: any) => s.id === created.body.id));
});

test('each call restores the Session\'s slot before it and saves it after', async () => {
  const id = (await call('POST', '/api/agent/sessions', BEA, {})).body.id;
  const from = llama.log.length;
  await call('POST', `/api/sessions/${id}/prompt`, BEA, { message: 'hola' });
  await settled(id, BEA);
  assert.deepEqual(llama.log.slice(from).map((l) => l.split(' ')[0]), ['restore', 'completion', 'save']);
});

test('the context window comes from the route: the composer reads the Local model, and pi plans by it', async () => {
  assert.deepEqual((await call('GET', '/api/models/llm', BEA)).body, { model: 'qwen-a', context_window: 65536 });
  const id = (await call('POST', '/api/agent/sessions', BEA, {})).body.id;
  await call('POST', `/api/sessions/${id}/prompt`, BEA, { message: 'hola' });
  await settled(id, BEA);
  const config = await call('GET', `/api/sessions/${id}/config`, BEA);
  assert.equal(config.body.live, true);
  assert.equal(config.body.state.model.id, 'qwen-a');
  assert.equal(config.body.state.model.contextWindow, 65536);
});

test('the admin switches the Local model; a live Session moves to it on its next turn, with the new window', async () => {
  const id = (await call('POST', '/api/agent/sessions', ANA, {})).body.id;
  await call('POST', `/api/sessions/${id}/prompt`, ANA, { message: 'antes' });
  await settled(id, ANA);
  assert.equal((await call('GET', '/api/models', ADMIN)).body.active.llm, 'qwen-a');
  const switched = await call('POST', '/api/models/activate', ADMIN, { id: 'qwen-b' });
  assert.deepEqual([switched.status, switched.body.active], [200, 'qwen-b']);
  await call('POST', `/api/sessions/${id}/prompt`, ANA, { message: 'después' });
  const events = await settled(id, ANA);
  assert.equal(llama.bodies.at(-1).model, 'qwen-b');
  assert.equal(assistantText(events).at(-1), 'hola');
  assert.equal((await call('GET', `/api/sessions/${id}/config`, ANA)).body.state.model.contextWindow, 131072);
  await call('POST', '/api/models/activate', ADMIN, { id: 'qwen-a' });
});

test('a switch while a turn is in course is a 409 the admin reads, from Deck or from the daemon', async () => {
  const id = (await call('POST', '/api/agent/sessions', ANA, {})).body.id;
  const release = llama.hold();
  await call('POST', `/api/sessions/${id}/prompt`, ANA, { message: 'largo' });
  for (let i = 0; i < 100 && !llama.log.at(-1)?.startsWith('completion'); i++) await new Promise((r) => setTimeout(r, 20));
  const busy = await call('POST', '/api/models/activate', ADMIN, { id: 'qwen-b' });
  release();
  await settled(id, ANA);
  assert.equal(busy.status, 409);
  assert.equal(busy.body.code, 'turns_in_flight');
  assert.match(busy.body.error, /turnos en curso/);
  assert.equal(daemon.activeModel, 'qwen-a');

  daemon.switchRefusal = 'lifecycle_busy';
  const daemonBusy = await call('POST', '/api/models/activate', ADMIN, { id: 'qwen-b' });
  daemon.switchRefusal = null;
  assert.deepEqual([daemonBusy.status, daemonBusy.body.code], [409, 'lifecycle_busy']);
  assert.match(daemonBusy.body.error, /ocupado/);
});

test("a Session whose owner is gone does not start, not even for an admin, and nothing falls back to the general Agent", async () => {
  const carl = daemon.addUser('carl', 'carl-password');
  const id = (await call('POST', '/api/agent/sessions', carl, {})).body.id;
  daemon.disable(carl);
  const before = llama.bodies.length;
  const refused = await call('POST', `/api/sessions/${id}/prompt`, ADMIN, { message: 'hola' });
  assert.deepEqual([refused.status, refused.body.code], [409, 'owner_gone']);
  assert.equal(llama.bodies.length, before);
});

test('only the admin lists and switches Local models', async () => {
  assert.equal((await call('GET', '/api/models', ANA)).status, 403);
  assert.equal((await call('POST', '/api/models/activate', ANA, { id: 'qwen-b' })).status, 403);
  assert.equal(daemon.activeModel, 'qwen-a');
});

test('a deleted Session takes its pi files and its saved slots with it', async () => {
  const id = (await call('POST', '/api/agent/sessions', BEA, {})).body.id;
  await call('POST', `/api/sessions/${id}/prompt`, BEA, { message: 'hola' });
  await settled(id, BEA);
  const before = readdirSync(slotsDir).length;
  assert.ok(existsSync(path.join(root, 'data', 'sessions', id)));
  assert.equal((await call('DELETE', `/api/sessions/${id}`, BEA)).status, 200);
  assert.equal(readdirSync(slotsDir).length, before - 1);
  assert.ok(!existsSync(path.join(root, 'data', 'sessions', id)));
  assert.equal((await call('GET', `/api/sessions/${id}`, BEA)).status, 404);
});

test('the event stream replays what was stored and then goes on live, ending the replay with caught-up', async () => {
  const id = (await call('POST', '/api/agent/sessions', ANA, {})).body.id;
  await call('POST', `/api/sessions/${id}/prompt`, ANA, { message: 'uno' });
  await settled(id, ANA);
  const controller = new AbortController();
  const res = await fetch(`${base}/api/sessions/${id}/events`, { headers: { cookie: cookie(ANA) }, signal: controller.signal });
  const reader = res.body!.getReader();
  let text = '';
  const until = async (pattern: RegExp) => {
    while (!pattern.test(text)) text += new TextDecoder().decode((await reader.read()).value);
  };
  await until(/event: caught-up/);
  assert.match(text, /"type":"portal_prompt"[^\n]*"uno"/);
  await call('POST', `/api/sessions/${id}/prompt`, ANA, { message: 'dos' });
  await until(/"type":"portal_prompt"[^\n]*"dos"[^]*"type":"agent_settled"/);
  controller.abort();
});

const guardVerdicts = (events: { type: string; payload: any }[]) =>
  events.filter((e) => e.type === 'portal_guard').map((e) => [e.payload.tool, e.payload.verdict]);

test('every call the Guard checks lands in the Session\'s transcript, and a refusal says why', async () => {
  await call('POST', '/api/workspaces', ADMIN, { name: 'guardado' });
  const id = (await call('POST', '/api/sessions', ADMIN, { workspace: 'guardado' })).body.id;
  // `echo curl` reads nothing, but the Guard judges the command: its output counts as fetched.
  llama.toolCalls = [{ name: 'bash', arguments: { command: 'echo curl' } }, { name: 'bash', arguments: { command: 'git push' } }];
  await call('POST', `/api/sessions/${id}/prompt`, ADMIN, { message: 'trae la página y publica' });
  const events = await settled(id, ADMIN);
  assert.deepEqual(guardVerdicts(events), [['bash', 'allow'], ['bash', 'deny']]);
  assert.match(events.find((e) => e.type === 'portal_guard' && e.payload.verdict === 'deny')!.payload.reason, /^publish:/);
  assert.match(promptText(llama.bodies.at(-1)), /Refused \(publish\)/);
});

test('a tainted Session stays tainted across a restart of Deck, even with its pi file gone', async () => {
  await call('POST', '/api/workspaces', ADMIN, { name: 'reinicio' });
  const id = (await call('POST', '/api/sessions', ADMIN, { workspace: 'reinicio' })).body.id;
  llama.toolCalls = [{ name: 'bash', arguments: { command: 'echo wget' } }];
  await call('POST', `/api/sessions/${id}/prompt`, ADMIN, { message: 'lee el correo' });
  await settled(id, ADMIN);

  await sessions.shutdown();
  const file = (await store.sessions.get(id))!.pi_session_file!;
  assert.ok(existsSync(file));
  rmSync(file);

  llama.toolCalls = [{ name: 'bash', arguments: { command: 'git push' } }];
  await call('POST', `/api/sessions/${id}/prompt`, ADMIN, { message: 'publica' });
  const events = await settled(id, ADMIN);
  assert.deepEqual(guardVerdicts(events).at(-1), ['bash', 'deny']);
});
