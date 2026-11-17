import { after, test } from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import http from 'node:http';
import net from 'node:net';
import type { AddressInfo } from 'node:net';
import { mkdirSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { FakeDaemon } from './helpers/fake-daemon.mts';
import { fakeLlama } from './helpers/fake-llama.mts';
// @ts-expect-error: a plain-JS double shared with the server's own tests.
import { FakeBrowserDriver } from '../server/test/helpers/fake-browser-driver.mjs';
// @ts-expect-error: a plain-JS double shared with the server's own tests.
import { fakeCdp } from '../server/test/helpers/fake-cdp.mjs';

/**
 * The Instance browser at Deck's HTTP surface (`createDeckApp`), composed as `index.ts` composes it:
 * the real Session manager running pi's SDK, the Guard and the browser tools, over a fake daemon, a
 * fake llama-server that answers with scripted tool calls, a fake CDP endpoint and a `BrowserDriver`
 * double (no Chrome, no container). The admin routes, the per-Session toggle, the `/browser-ui`
 * view and who may drive the browser from a Session.
 */
const SECRET = 'instance-browser-test-secret';
process.env.RINTHEL_PANEL_SECRET = SECRET;
const root = mkdtempSync(path.join(tmpdir(), 'deck-browser-'));
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
const { FsInstanceSoul } = await import('../server/src/instance-soul-fs.ts');
const { browserSettings } = await import('../server/src/browser-settings.ts');
const { InMemoryBrowserRuntime } = await import('../server/src/instance-browser.ts');
const { attachBrowserUpgrade } = await import('../server/src/browser-proxy.ts');

const slotsDir = path.join(root, 'data', 'llama-slots');
const llama = await fakeLlama(slotsDir);
const cdp = await fakeCdp();
const daemon = new FakeDaemon(SECRET);
const ADMIN = daemon.addUser('root', 'root-password', 'admin');
const ANA = daemon.addUser('ana', 'ana-password');
daemon.models = [{ id: 'qwen-a', context_window: 65536 }];
daemon.activeModel = 'qwen-a';
daemon.llamaUrl = llama.url;

// A port nobody listens on: an admin who gets past the view's guard meets a browser that is not there.
const probe = net.createServer().listen(0, '127.0.0.1');
await once(probe, 'listening');
const deadPort = (probe.address() as AddressInfo).port;
await new Promise<void>((r) => probe.close(() => r()));

const store = createMemoryStore();
const identity = daemonSessionIdentity(daemon);
const routing = new DaemonModelRouting(daemon);
const slots = new SessionSlots(new LlamaSlotStore(slotsDir), { maxBytes: 1_000_000 });
const roots = new FsSessionRoots(path.join(root, 'data'), path.join(root, 'data', 'workspaces'));
const settings = browserSettings(store.settings, { httpsPort: String(deadPort) });
const runtime = new InMemoryBrowserRuntime();
const driver = new FakeBrowserDriver([
  { name: 'browser_navigate', description: 'Go to a URL', inputSchema: { type: 'object', properties: { url: { type: 'string' } }, required: ['url'] } },
  { name: 'browser_snapshot', description: 'Read the page', inputSchema: { type: 'object', properties: {} } },
  { name: 'browser_run_code_unsafe', description: 'Run code', inputSchema: { type: 'object', properties: {} } },
], () => ({ content: [{ type: 'text', text: 'Página de ejemplo' }], isError: false }));
let sessions: InstanceType<typeof SessionManager>;
const proxy = new SessionProxy({
  routing, slots,
  onProgress: (id, prefill) => sessions.reportPrefill(id, prefill),
  onRoute: (id, route) => sessions.reportRoute(id, route),
});
await proxy.start();
const canvases = createCanvases(store);
const instanceSoul = new FsInstanceSoul(path.join(root, 'data', 'instance', 'SOUL.md'));
sessions = new SessionManager({
  store, identity, proxy, roots, canvases, instanceSoulFile: instanceSoul.path,
  launch: (opts) => SdkPiClient.create(opts),
  browser: { driver, cdpEndpoint: cdp.url, allowlist: () => settings.allowlist() },
});
const app = createDeckApp({
  store, daemon, identity, serviceSecret: 'svc', sessions, roots, slots, routing, canvases,
  canvasActions: createCanvasActions({ canvases, notes: storedSessionNotes(store) }), instanceSoul,
  webDist: path.join(root, 'no-web'),
  browser: { settings, runtime, cdpUrl: cdp.url, uiHost: '127.0.0.1' },
});
const server = http.createServer(app);
attachBrowserUpgrade(server, { settings, identity, host: '127.0.0.1' });
server.listen(0, '127.0.0.1');
await once(server, 'listening');
const port = (server.address() as AddressInfo).port;
const base = `http://127.0.0.1:${port}`;
after(async () => {
  await sessions.shutdown();
  proxy.stop();
  server.closeAllConnections();
  await new Promise<void>((r) => server.close(() => r()));
  await llama.close();
  await cdp.close();
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

async function settled(id: string, as: number) {
  for (let i = 0; i < 200; i++) {
    const s = await call('GET', `/api/sessions/${id}`, as);
    if (s.body.status === 'idle' || s.body.status === 'error') break;
    await new Promise((r) => setTimeout(r, 25));
  }
  await slots.idle();
  return (await call('GET', `/api/sessions/${id}/events/before?before=999999999`, as)).body.events as { type: string; payload: any }[];
}

const guardNotices = (events: { type: string; payload: any }[]) => events.filter((e) => e.type === 'portal_guard').map((e) => [e.payload.tool, e.payload.verdict]);

/** A Turn whose model calls `browser_navigate` once, then answers. */
async function navigateTurn(id: string, as: number, url = 'https://example.com/') {
  llama.toolCalls = [{ name: 'browser_navigate', arguments: { url } }];
  const sent = await call('POST', `/api/sessions/${id}/prompt`, as, { message: 'abre la página' });
  assert.equal(sent.status, 200, JSON.stringify(sent.body));
  return settled(id, as);
}

test('a miembro gets a 403 on every browser route, reading included, and nothing is written', async () => {
  const id = (await call('POST', '/api/agent/sessions', ANA, {})).body.id;
  const routes: Array<[string, string, unknown?]> = [
    ['GET', '/api/browser'],
    ['POST', '/api/browser/install'],
    ['POST', '/api/browser/start'],
    ['POST', '/api/browser/stop'],
    ['DELETE', '/api/browser/install'],
    ['PUT', '/api/browser/config', { password: 'x' }],
    ['GET', '/api/browser/suggest-password'],
    ['PUT', '/api/browser/allowlist', { domains: 'a.example' }],
    ['PUT', `/api/sessions/${id}/browser`, { enabled: true }],
  ];
  for (const [method, url, body] of routes) {
    const res = await call(method, url, ANA, body);
    assert.equal(res.status, 403, `${method} ${url}`);
    assert.equal(res.body.error, 'Solo el administrador puede usar el browser de la Instance.');
  }
  assert.deepEqual(await settings.allowlist(), []);
  assert.equal((await store.sessions.get(id))?.browser, 0);
  assert.equal((await settings.config()).password, '');
  assert.deepEqual(runtime.log, []);
});

test('the admin installs the browser only with a password, then stops and starts it; nothing stops it by itself', async () => {
  const refused = await call('POST', '/api/browser/install', ADMIN);
  assert.equal(refused.status, 400);
  assert.match(refused.body.error, /password/);
  const suggested = (await call('GET', '/api/browser/suggest-password', ADMIN)).body.password;
  assert.match(suggested, /^[0-9a-f]{24}$/);
  const saved = await call('PUT', '/api/browser/config', ADMIN, { password: suggested, user: 'agente' });
  assert.deepEqual(saved.body, { user: 'agente', hasPassword: true });
  assert.equal((await call('POST', '/api/browser/install', ADMIN)).status, 200);
  assert.equal((await call('POST', '/api/browser/stop', ADMIN)).status, 200);
  assert.equal((await call('POST', '/api/browser/start', ADMIN)).status, 200);
  assert.deepEqual(runtime.log, ['install', 'stop', 'start']);
  const status = (await call('GET', '/api/browser', ADMIN)).body;
  assert.equal(status.install.container, 'running');
  assert.deepEqual(status.config, { user: 'agente', hasPassword: true });
  assert.equal(JSON.stringify(status).includes(suggested), false, 'the password is never sent back');
});

test('the status reads the fixed CDP endpoint: version, open pages, and the Sessions that may drive it', async () => {
  const id = (await call('POST', '/api/agent/sessions', ADMIN, {})).body.id;
  assert.deepEqual((await call('PUT', `/api/sessions/${id}/browser`, ADMIN, { enabled: true })).body, { enabled: true });
  const status = (await call('GET', '/api/browser', ADMIN)).body;
  assert.equal(status.running, true);
  assert.equal(status.version, 'Chrome/130.0');
  assert.deepEqual(status.pages, [{ title: 'Inicio', url: 'https://example.com/' }]);
  assert.ok(status.sessions.some((s: any) => s.id === id));
  assert.equal((await call('PUT', '/api/sessions/nope/browser', ADMIN, { enabled: true })).status, 404);
  await call('PUT', `/api/sessions/${id}/browser`, ADMIN, { enabled: false });
  cdp.state.up = false;
  try {
    assert.equal((await call('GET', '/api/browser', ADMIN)).body.running, false);
  } finally { cdp.state.up = true; }
});

test('the allowlist is saved in the settings and read back as lines; a body without it is a 400', async () => {
  const saved = await call('PUT', '/api/browser/allowlist', ADMIN, { domains: ' a.example, *.b.example ' });
  assert.equal(saved.body.allowlist, 'a.example\n*.b.example');
  assert.deepEqual(await settings.allowlist(), ['a.example', '*.b.example']);
  assert.equal((await call('PUT', '/api/browser/allowlist', ADMIN, {})).status, 400);
  await call('PUT', '/api/browser/allowlist', ADMIN, { domains: '' });
});

test('an admin Session with the browser on navigates the Instance browser through its own tools, at the fixed CDP endpoint', async () => {
  const id = (await call('POST', '/api/agent/sessions', ADMIN, {})).body.id;
  await call('PUT', `/api/sessions/${id}/browser`, ADMIN, { enabled: true });
  const before = driver.calls.length;
  const events = await navigateTurn(id, ADMIN);
  assert.deepEqual(driver.calls.slice(before).map((c: any) => [c.endpoint, c.tool, c.args.url]), [[cdp.url, 'browser_navigate', 'https://example.com/']]);
  assert.deepEqual(guardNotices(events), [['browser_navigate', 'allow']]);
  const offered = llama.bodies.at(-1).tools.map((t: any) => t.function.name);
  assert.ok(offered.includes('browser_snapshot'));
  assert.equal(offered.includes('browser_run_code_unsafe'), false, 'arbitrary code is never offered');
  // What the page said is someone else's words: the Session is tainted for good.
  assert.equal(await store.sessionTaint.isTainted(id), true);
});

test('two admin Sessions share the one Instance browser, with no lease', async () => {
  const a = (await call('POST', '/api/agent/sessions', ADMIN, {})).body.id;
  const b = (await call('POST', '/api/agent/sessions', ADMIN, {})).body.id;
  for (const id of [a, b]) await call('PUT', `/api/sessions/${id}/browser`, ADMIN, { enabled: true });
  const before = driver.calls.length;
  await navigateTurn(a, ADMIN, 'https://a.example/');
  await navigateTurn(b, ADMIN, 'https://b.example/');
  assert.deepEqual(driver.calls.slice(before).map((c: any) => c.endpoint), [cdp.url, cdp.url]);
});

test('an admin Session with the toggle off is refused, and turning it on applies on the next call, with no relaunch', async () => {
  const id = (await call('POST', '/api/agent/sessions', ADMIN, {})).body.id;
  const before = driver.calls.length;
  const refused = await navigateTurn(id, ADMIN);
  assert.deepEqual(guardNotices(refused), [['browser_navigate', 'deny']]);
  assert.equal(driver.calls.length, before);
  await call('PUT', `/api/sessions/${id}/browser`, ADMIN, { enabled: true });
  await navigateTurn(id, ADMIN);
  assert.equal(driver.calls.length, before + 1);
});

test('a URL off the allowlist is refused before the browser is reached', async () => {
  const id = (await call('POST', '/api/agent/sessions', ADMIN, {})).body.id;
  await call('PUT', `/api/sessions/${id}/browser`, ADMIN, { enabled: true });
  await call('PUT', '/api/browser/allowlist', ADMIN, { domains: '*.example.com' });
  try {
    const before = driver.calls.length;
    const events = await navigateTurn(id, ADMIN, 'https://evil.test/');
    assert.deepEqual(guardNotices(events), [['browser_navigate', 'deny']]);
    assert.equal(driver.calls.length, before);
  } finally { await call('PUT', '/api/browser/allowlist', ADMIN, { domains: '' }); }
});

test('a miembro\'s Session never opens the browser, even with its toggle on in the store: no tools offered, any call refused', async () => {
  const id = (await call('POST', '/api/agent/sessions', ANA, {})).body.id;
  await store.sessions.setBrowser(id, true);
  const before = driver.calls.length;
  const events = await navigateTurn(id, ANA);
  // A closed profile has no such tool: pi refuses it before the Guard is asked, and nothing allows it.
  assert.equal(guardNotices(events).some(([, verdict]) => verdict === 'allow'), false);
  assert.equal(driver.calls.length, before);
  assert.equal(llama.bodies.at(-1).tools.some((t: any) => t.function.name.startsWith('browser_')), false);
});

test('an admin demoted after the Session started loses the browser on the next call', async () => {
  const LUIS = daemon.addUser('luis', 'luis-password', 'admin');
  const id = (await call('POST', '/api/agent/sessions', LUIS, {})).body.id;
  await call('PUT', `/api/sessions/${id}/browser`, LUIS, { enabled: true });
  await navigateTurn(id, LUIS);
  const before = driver.calls.length;
  // The daemon's record of the user changes; nothing in Deck is told.
  (daemon as unknown as { users: Map<number, { role: string }> }).users.get(LUIS)!.role = 'miembro';
  const events = await navigateTurn(id, LUIS);
  // Only the first Turn's call was ever allowed (the events are the whole Session's).
  assert.deepEqual(guardNotices(events).filter(([tool, verdict]) => tool === 'browser_navigate' && verdict === 'allow').length, 1);
  assert.equal(driver.calls.length, before);
});

// The view: `/browser-ui` and its websocket.
const view = (as?: number) => fetch(`${base}/browser-ui/vnc.html`, { headers: as === undefined ? {} : { cookie: cookie(as) } });

async function upgradeStatus(as?: number): Promise<string> {
  const socket = net.connect(port, '127.0.0.1');
  await once(socket, 'connect');
  socket.write(
    `GET /browser-ui/websockify HTTP/1.1\r\nHost: x\r\nConnection: Upgrade\r\nUpgrade: websocket\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n${as === undefined ? '' : `Cookie: ${cookie(as)}\r\n`}\r\n`,
  );
  const [chunk] = await once(socket, 'data');
  socket.destroy();
  return String(chunk).split('\r\n')[0];
}

test('/browser-ui answers 403 to a miembro and 401 without a valid cookie, over HTTP and websocket', async () => {
  assert.equal((await view(ANA)).status, 403);
  assert.equal((await view()).status, 401);
  assert.match(await upgradeStatus(ANA), /403/);
  assert.match(await upgradeStatus(), /401/);
});

test('/browser-ui lets an admin through to the browser (not running here, so 502 with its own reason)', async () => {
  const res = await view(ADMIN);
  assert.equal(res.status, 502);
  assert.match(await res.text(), /^The browser is not answering/);
});
