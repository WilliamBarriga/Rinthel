import { after, test } from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import type { AddressInfo } from 'node:net';
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { FakeDaemon } from './helpers/fake-daemon.mts';

/**
 * Deck's HTTP surface as the browser and the daemon reach it: the app `index.ts` serves
 * (`createDeckApp`), over the in-memory store and the fake daemon, so no disk, pi or daemon is
 * reached. Login, logout and refresh; the users screen relayed to the daemon, admin only; and the
 * daemon's service credential, which opens `POST /agent/retire-sessions` and nothing else.
 */
const SECRET = 'server-routes-secret';
const SERVICE = 'service-secret-of-the-instance';
// `identity.ts` reads the secret when it is imported.
process.env.RINTHEL_PANEL_SECRET = SECRET;

const { createMemoryStore } = await import('../server/src/store/memory/index.ts');
const { createDeckApp } = await import('../server/src/app.ts');
const { ACCESS_COOKIE } = await import('../server/src/identity.ts');
const { daemonSessionIdentity } = await import('../server/src/daemon-session-identity.ts');

const store = createMemoryStore();
const daemon = new FakeDaemon(SECRET);
const ADMIN_ID = daemon.addUser('root', 'root-password', 'admin');
const ANA_ID = daemon.addUser('ana', 'ana-password');
const BEA_ID = daemon.addUser('bea', 'bea-password');
const stopped: string[] = [];

const webDist = mkdtempSync(path.join(tmpdir(), 'deck-web-dist-'));
mkdirSync(path.join(webDist, 'assets'));
writeFileSync(path.join(webDist, 'index.html'), '<html>deck</html>');

const app = createDeckApp({
  store,
  daemon,
  identity: daemonSessionIdentity(daemon),
  serviceSecret: SERVICE,
  runtime: { stop: async (id: string) => void stopped.push(id) },
  webDist,
});
const server = app.listen(0, '127.0.0.1');
await once(server, 'listening');
const base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
after(async () => {
  server.closeAllConnections();
  await new Promise<void>((r) => server.close(() => r()));
  rmSync(webDist, { recursive: true, force: true });
});

type Opts = { cookie?: string; body?: unknown; headers?: Record<string, string> };
async function call(method: string, url: string, opts: Opts = {}) {
  const res = await fetch(`${base}${url}`, {
    method,
    headers: { 'content-type': 'application/json', ...(opts.cookie ? { cookie: opts.cookie } : {}), ...opts.headers },
    body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
  });
  const text = await res.text();
  let body: any = text;
  try { body = JSON.parse(text); } catch { /* the static files */ }
  return { status: res.status, body, cookies: res.headers.getSetCookie() };
}
const access = (id: number, ttl?: number) => `${ACCESS_COOKIE}=${daemon.accessToken(id, ttl)}`;
const cookieHeader = (setCookies: string[]) => setCookies.map((c) => c.split(';')[0]).filter((c) => !c.endsWith('=')).join('; ');
const login = async (username: string, password: string) => cookieHeader((await call('POST', '/api/auth/login', { body: { username, password } })).cookies);
const service = (userId?: number, secret = SERVICE) => ({
  'x-rinthel-service-secret': secret,
  ...(userId === undefined ? {} : { 'x-rinthel-user-id': String(userId) }),
});

// --- login, logout, refresh ---

test('status: no login yet, a login is always required', async () => {
  assert.deepEqual((await call('GET', '/api/auth/status')).body, { authRequired: true, authed: false });
});

test('login needs both fields, refuses a wrong password and sets the two cookies on a right one', async () => {
  assert.equal((await call('POST', '/api/auth/login', { body: { username: 'ana' } })).status, 400);
  const wrong = await call('POST', '/api/auth/login', { body: { username: 'ana', password: 'nope' } });
  assert.equal(wrong.status, 401);
  assert.deepEqual(wrong.cookies, []);

  const ok = await call('POST', '/api/auth/login', { body: { username: 'ana', password: 'ana-password' } });
  assert.deepEqual([ok.status, ok.body], [200, { ok: true }]);
  assert.ok(ok.cookies.some((c) => c.startsWith(`${ACCESS_COOKIE}=`)));
  assert.ok(ok.cookies.some((c) => c.startsWith('pi_panel_refresh=')));
});

test('status after login: the role the Instance has now and the username', async () => {
  const cookie = await login('root', 'root-password');
  assert.deepEqual((await call('GET', '/api/auth/status', { cookie })).body, { authRequired: true, authed: true, role: 'admin', username: 'root' });
  const member = await login('ana', 'ana-password');
  assert.deepEqual((await call('GET', '/api/auth/status', { cookie: member })).body, { authRequired: true, authed: true, role: 'miembro', username: 'ana' });
});

test('an expired access token is refreshed with the refresh cookie, once: the refresh token rotates', async () => {
  const cookie = await login('bea', 'bea-password');
  const refresh = cookie.split('; ').find((c) => c.startsWith('pi_panel_refresh='))!;
  const expired = `${access(BEA_ID, -10)}; ${refresh}`;

  const first = await call('GET', '/api/identity/users', { cookie: expired });
  // A member: the refresh worked (403, not 401) and new cookies came back.
  assert.equal(first.status, 403);
  assert.ok(first.cookies.some((c) => c.startsWith(`${ACCESS_COOKIE}=`) && !c.startsWith(`${ACCESS_COOKIE}=;`)));

  const replayed = await call('GET', '/api/identity/users', { cookie: expired });
  assert.equal(replayed.status, 401, 'a used refresh token does not work twice');
});

test('logout revokes the login: the same access token is refused afterwards and the cookies are cleared', async () => {
  const cookie = await login('ana', 'ana-password');
  assert.equal((await call('GET', '/api/auth/status', { cookie })).body.authed, true);
  const out = await call('POST', '/api/auth/logout', { cookie });
  assert.equal(out.status, 200);
  assert.ok(out.cookies.some((c) => c.startsWith(`${ACCESS_COOKIE}=;`)));
  assert.equal((await call('GET', '/api/identity/users', { cookie })).status, 401);
});

test('no cookie at all is a 401 on every route behind the login', async () => {
  assert.equal((await call('GET', '/api/identity/users')).status, 401);
});

// --- users, admin only ---

test('a member does not reach the users: 403 with the reason in Spanish', async () => {
  const res = await call('GET', '/api/identity/users', { cookie: access(ANA_ID) });
  assert.equal(res.status, 403);
  assert.match(res.body.error, /Solo el administrador/);
  assert.equal((await call('DELETE', `/api/identity/users/${BEA_ID}`, { cookie: access(ANA_ID) })).status, 403);
  assert.ok(daemon.has(BEA_ID));
});

test('the admin lists, creates, edits and deletes users through the daemon', async () => {
  const cookie = access(ADMIN_ID);
  const list = await call('GET', '/api/identity/users', { cookie });
  assert.equal(list.status, 200);
  assert.ok(list.body.users.some((u: any) => u.username === 'ana'));
  assert.ok(list.body.users.every((u: any) => !('password' in u)));

  const created = await call('POST', '/api/identity/users', { cookie, body: { username: 'caro', password: 'caro-password', role: 'miembro' } });
  assert.equal(created.status, 200);
  const taken = await call('POST', '/api/identity/users', { cookie, body: { username: 'caro', password: 'caro-password', role: 'miembro' } });
  assert.deepEqual([taken.status, taken.body.detail.code], [409, 'username_taken']);

  const edited = await call('PATCH', `/api/identity/users/${created.body.id}`, { cookie, body: { notes: 'ventas' } });
  assert.deepEqual([edited.status, edited.body.notes], [200, 'ventas']);

  assert.equal((await call('DELETE', `/api/identity/users/${created.body.id}`, { cookie })).status, 200);
  assert.ok(!daemon.has(created.body.id));
});

test('the admin cannot lock themselves out: the daemon refusal comes through', async () => {
  const res = await call('DELETE', `/api/identity/users/${ADMIN_ID}`, { cookie: access(ADMIN_ID) });
  assert.deepEqual([res.status, res.body.detail.code], [409, 'self_lockout']);
});

test('only users are relayed under /identity: login, session-principal and the rest are not', async () => {
  const cookie = access(ADMIN_ID);
  assert.equal((await call('GET', '/api/identity/me/session-principal', { cookie })).status, 404);
  assert.equal((await call('GET', '/api/identity/groups', { cookie })).status, 404);
});

test('a demoted admin loses the users on the next request, not when the token expires', async () => {
  const id = daemon.addUser('temp-admin', 'temp-password', 'admin');
  const cookie = access(id);
  assert.equal((await call('GET', '/api/identity/users', { cookie })).status, 200);
  await call('PATCH', `/api/identity/users/${id}`, { cookie: access(ADMIN_ID), body: { role: 'miembro' } });
  assert.equal((await call('GET', '/api/identity/users', { cookie })).status, 403);
});

// --- the daemon's service credential ---

test('retire-sessions: the daemon retires every Session the user owns, stopping each first, and only theirs', async () => {
  await store.sessions.create({ id: 'ana-task', title: 't', workspace: '/w', executor: 'host', owner_user_id: ANA_ID });
  await store.sessions.create({ id: 'ana-agent', title: 'a', workspace: '/h', executor: 'host', kind: 'agent', owner_user_id: ANA_ID });
  await store.sessions.create({ id: 'bea-task', title: 'b', workspace: '/w', executor: 'host', owner_user_id: BEA_ID });
  await store.sessions.appendEvent('ana-task', 'text', {});

  const res = await call('POST', '/api/agent/retire-sessions', { headers: service(ANA_ID), body: {} });
  assert.deepEqual([res.status, res.body], [200, { retired: 2 }]);
  assert.deepEqual(stopped.sort(), ['ana-agent', 'ana-task']);
  assert.equal(await store.sessions.get('ana-task'), undefined);
  assert.deepEqual(await store.sessions.eventsSince('ana-task'), []);
  assert.ok(await store.sessions.get('bea-task'));

  const again = await call('POST', '/api/agent/retire-sessions', { headers: service(ANA_ID), body: {} });
  assert.deepEqual(again.body, { retired: 0 }, 'idempotent');
});

test('retire-sessions works for a user the daemon already disabled', async () => {
  const id = daemon.addUser('gone', 'gone-password');
  await store.sessions.create({ id: 'gone-task', title: 'g', workspace: '/w', executor: 'host', owner_user_id: id });
  daemon.disable(id);
  const res = await call('POST', '/api/agent/retire-sessions', { headers: service(id), body: {} });
  assert.deepEqual([res.status, res.body], [200, { retired: 1 }]);
});

test('retire-sessions is the service credential only: a cookie, an admin one too, is refused', async () => {
  await store.sessions.create({ id: 'bea-2', title: 'b', workspace: '/w', executor: 'host', owner_user_id: BEA_ID });
  const res = await call('POST', '/api/agent/retire-sessions', { cookie: access(ADMIN_ID), body: {} });
  assert.equal(res.status, 403);
  assert.ok(await store.sessions.get('bea-2'));
});

test('every refusal of the credential is a 401: wrong or empty secret, no user, a bad id', async () => {
  for (const headers of [service(BEA_ID, 'wrong'), service(BEA_ID, ''), service(), { ...service(), 'x-rinthel-user-id': '0' }, { ...service(), 'x-rinthel-user-id': 'abc' }]) {
    const res = await call('POST', '/api/agent/retire-sessions', { headers, body: {} });
    assert.deepEqual([res.status, res.body], [401, { error: 'Unauthorized' }], JSON.stringify(headers));
  }
  assert.ok(await store.sessions.get('bea-task'));
});

test('the credential opens no other route, and its cookies are dropped: a valid admin cookie does not rescue it', async () => {
  for (const [method, url] of [['GET', '/api/identity/users'], ['GET', '/api/auth/status'], ['POST', '/api/agent/retire-sessions/']] as const) {
    const res = await call(method, url, { headers: service(ADMIN_ID), cookie: access(ADMIN_ID), body: method === 'POST' ? {} : undefined });
    assert.equal(res.status, 401, `${method} ${url}`);
  }
  const bad = await call('GET', '/api/identity/users', { headers: service(ADMIN_ID, 'wrong'), cookie: access(ADMIN_ID) });
  assert.equal(bad.status, 401);
});

// --- the SPA ---

test('the built web UI is served for every path that is not /api', async () => {
  assert.equal((await call('GET', '/users')).body, '<html>deck</html>');
  assert.equal((await call('GET', '/api/nope', { cookie: access(ADMIN_ID) })).status, 404);
});
