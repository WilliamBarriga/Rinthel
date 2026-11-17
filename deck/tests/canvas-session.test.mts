import { test } from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { FakeDaemon } from './helpers/fake-daemon.mts';
import { createMemoryStore } from '../server/src/store/memory/index.ts';
import { daemonSessionIdentity } from '../server/src/daemon-session-identity.ts';
import { InMemorySessionRoots } from '../server/src/session-roots.ts';
import { SessionManager, canvasNotesBlock } from '../server/src/session-manager.ts';
import { createCanvases } from '../server/src/canvases.ts';
import { CanvasTools, CANVAS_TOOLS } from '../server/src/pi/canvas-tools.ts';
import { extraContextFiles, type SdkLaunch } from '../server/src/pi/sdk-client.ts';
import { MEMBER_TOOLS } from '../server/src/tool-profile.ts';

/**
 * What the surfaces add to a running Session, through the `SessionManager` with a pi double: a
 * member's Session gets the canvas tools and the Instance SOUL (an admin's keeps their own SOUL),
 * and what the person left through a Canvas reaches the Agent with the next prompt, never before.
 */
const daemon = new FakeDaemon('canvas-session-secret');
const ADMIN = daemon.addUser('root', 'root-password', 'admin');
const ANA = daemon.addUser('ana', 'ana-password');

function setup(failPrompt = false) {
  const store = createMemoryStore();
  const canvases = createCanvases(store);
  const launched: SdkLaunch[] = [];
  const prompted: string[] = [];
  const pi = () => Object.assign(new EventEmitter(), {
    running: true,
    sessionFile: undefined,
    profile: { kind: 'general' },
    prompt: async (message: string) => { if (failPrompt) throw new Error('no model'); prompted.push(message); },
    abort: async () => {},
    isIdle: () => true,
    dispose() { this.emit('exit', { code: 0, signal: null }); },
    getCommands: async () => [],
    respondUi: () => false,
  });
  const manager = new SessionManager({
    store,
    identity: daemonSessionIdentity(daemon),
    proxy: { open: async () => ({ url: 'http://x', route: () => null }) as any, close: () => {} },
    roots: new InMemorySessionRoots(),
    canvases,
    instanceSoulFile: '/instance/SOUL.md',
    launch: async (opts) => { launched.push(opts); return pi() as any; },
  });
  return { store, manager, launched, prompted };
}

test('a member\'s Session launches with the canvas tools and the Instance SOUL; an admin\'s with the canvases and their own SOUL', async () => {
  const { store, manager, launched } = setup();
  await store.sessions.create({ id: 'm', title: 'm', workspace: '/w', executor: 'host', kind: 'agent', owner_user_id: ANA });
  await store.sessions.create({ id: 'a', title: 'a', workspace: '/w', executor: 'host', kind: 'agent', owner_user_id: ADMIN });
  await manager.prompt('m', 'hola');
  await manager.prompt('a', 'hola');
  const member = launched.find((l) => l.sessionId === 'm')!;
  const admin = launched.find((l) => l.sessionId === 'a')!;
  assert.deepEqual(member.profile, { kind: 'miembro', tools: CANVAS_TOOLS });
  assert.equal(member.instanceSoulFile, '/instance/SOUL.md');
  assert.ok(member.canvases && admin.canvases);
  assert.equal(admin.profile.kind, 'general');
  assert.equal(admin.instanceSoulFile, undefined);
  await manager.shutdown();
});

test('a member\'s Agent may call the canvas tools and nothing else', () => {
  const tools: string[] = [];
  new CanvasTools('s', createCanvases(createMemoryStore())).extension({ registerTool: (t: any) => tools.push(t.name) } as any);
  assert.deepEqual([...tools].sort(), [...MEMBER_TOOLS].sort());
});

test('a message left through a Canvas reaches the Agent with the next prompt, once', async () => {
  const { store, manager, prompted } = setup();
  await store.sessions.create({ id: 'm', title: 'm', workspace: '/w', executor: 'host', kind: 'agent', owner_user_id: ANA });
  await store.sessions.addNote('m', 'Quiero el informe de ventas');
  assert.deepEqual(prompted, []);
  await manager.prompt('m', 'sigue');
  assert.equal(prompted.length, 1);
  assert.equal(prompted[0], `${canvasNotesBlock(['Quiero el informe de ventas'])}\n\nsigue`);
  await manager.prompt('m', 'otra');
  assert.equal(prompted[1], 'otra');
  await manager.shutdown();
});

test('a prompt that fails keeps the Canvas messages for the next one', async () => {
  const { store, manager } = setup(true);
  await store.sessions.create({ id: 'm', title: 'm', workspace: '/w', executor: 'host', kind: 'agent', owner_user_id: ANA });
  await store.sessions.addNote('m', 'no lo pierdas');
  await assert.rejects(manager.prompt('m', 'hola'), /no model/);
  assert.deepEqual(await store.sessions.takeNotes('m'), ['no lo pierdas']);
  await manager.shutdown();
});

test('context files: a member loads the Instance SOUL, never a SOUL.md of their home; an admin loads their own', () => {
  const root = mkdtempSync(path.join(tmpdir(), 'deck-soul-ctx-'));
  try {
    const home = path.join(root, 'home');
    mkdirSync(home);
    writeFileSync(path.join(home, 'SOUL.md'), 'own soul\n');
    writeFileSync(path.join(home, 'MEMORY.md'), 'memory\n');
    const instance = path.join(root, 'SOUL.md');
    writeFileSync(instance, 'instance soul\n');

    const member = extraContextFiles(home, instance);
    assert.deepEqual(member.map((f) => [f.name, f.content]), [['SOUL.md', 'instance soul\n'], ['MEMORY.md', 'memory\n']]);
    assert.deepEqual(extraContextFiles(home).map((f) => [f.name, f.content]), [['SOUL.md', 'own soul\n'], ['MEMORY.md', 'memory\n']]);
    // Not defined (yet): the member loads no SOUL at all, not the one in their home.
    assert.deepEqual(extraContextFiles(home, path.join(root, 'missing.md')).map((f) => f.name), ['MEMORY.md']);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
