import { after, test } from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import type { AddressInfo } from 'node:net';
import { readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import express from 'express';
import cookieParser from 'cookie-parser';
import { FakeDaemon } from './helpers/fake-daemon.mts';

// The routers under api/ (and the pass-through) answer from what they are given: the in-memory store and the fake
// daemon, so no file or daemon is reached. And the front's adapters read what the real routers write.

const SECRET = 'api-routers-secret';
process.env.RINTHEL_PANEL_SECRET = SECRET;
const { createMemoryStore } = await import('../server/src/store/memory/index.ts');
const { serviceCredential } = await import('../server/src/service-credential.ts');
const { userSessionsRouter } = await import('../server/src/api/user-sessions.ts');
const { requireAuth, ACCESS_COOKIE } = await import('../server/src/identity.ts');
const { daemonProxyRouter } = await import('../server/src/daemon-proxy.ts');
const { fetchUsersAdminApi } = await import('../web/src/ports/adapters/fetch-users-admin.ts');
const { UsersAdminConflict } = await import('../web/src/ports/users-admin.ts');

const store = createMemoryStore();
const daemon = new FakeDaemon(SECRET);
const admin = daemon.addUser('root', 'root-password', 'admin');
const ana = daemon.addUser('ana', 'ana-password');

const app = express();
app.use(express.json());
app.use(cookieParser());
app.use('/api', serviceCredential({ secret: 'svc' }));
app.use('/api', requireAuth(daemon));
app.use('/api', userSessionsRouter({ store, runtime: { stop: async () => {} } }));
app.use('/api', daemonProxyRouter(daemon));
const server = app.listen(0, '127.0.0.1');
await once(server, 'listening');
const origin = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
after(async () => {
  server.closeAllConnections();
  await new Promise<void>((r) => server.close(() => r()));
});

test('retire-sessions deletes from the store it is given, and only the owner\'s', async () => {
  await store.sessions.create({ id: 'a', title: 'a', workspace: '/w', executor: 'host', owner_user_id: ana });
  await store.sessions.create({ id: 'b', title: 'b', workspace: '/w', executor: 'host', owner_user_id: admin });
  const res = await fetch(`${origin}/api/agent/retire-sessions`, {
    method: 'POST', headers: { 'content-type': 'application/json', 'x-rinthel-service-secret': 'svc', 'x-rinthel-user-id': String(ana) }, body: '{}',
  });
  assert.deepEqual(await res.json(), { retired: 1 });
  assert.equal(await store.sessions.get('a'), undefined);
  assert.ok(await store.sessions.get('b'));
});

test('nothing under api/ reaches a store singleton or opens the database itself', () => {
  const dir = path.resolve(import.meta.dirname, '../server/src/api');
  const offenders = readdirSync(dir)
    .filter((f) => f.endsWith('.ts') && /\bgetStore\b|store\/index|store\/sqlite|better-sqlite3/.test(readFileSync(path.join(dir, f), 'utf8')));
  assert.deepEqual(offenders, []);
});

test("the front's users adapter reads what the real pass-through relays: paths, bodies and the typed 409", async () => {
  const cookie = `${ACCESS_COOKIE}=${daemon.accessToken(admin)}`;
  // The adapter's own fetch, pointed at the real router: any drift in a path or in a body shows here.
  const api = fetchUsersAdminApi((input, init) => fetch(`${origin}${String(input)}`, { ...init, headers: { ...(init?.headers as Record<string, string>), cookie } }));

  assert.deepEqual((await api.listUsers()).map((u) => u.username), ['root', 'ana']);
  const dora = await api.createUser({ username: 'dora', password: 'dora-password', role: 'miembro' });
  assert.equal(dora.username, 'dora');
  assert.equal((await api.updateUser(dora.id, { notes: 'x' })).notes, 'x');
  const refused = await api.deleteUser(admin).catch((e: unknown) => e);
  assert.ok(refused instanceof UsersAdminConflict);
  assert.equal((refused as InstanceType<typeof UsersAdminConflict>).code, 'self_lockout');
  await api.deleteUser(dora.id);
  assert.ok(!daemon.has(dora.id));
});
