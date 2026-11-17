import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';
import { fetchAuthApi } from '../web/src/ports/adapters/fetch-auth.ts';
import { fetchUsersAdminApi } from '../web/src/ports/adapters/fetch-users-admin.ts';
import { fetchSessionsApi } from '../web/src/ports/adapters/fetch-sessions.ts';
import { fetchModelsApi } from '../web/src/ports/adapters/fetch-models.ts';
import { fetchCanvasesApi } from '../web/src/ports/adapters/fetch-canvases.ts';
import { fetchAppearanceApi } from '../web/src/ports/adapters/fetch-appearance.ts';
import { fetchInstanceSoulApi } from '../web/src/ports/adapters/fetch-instance-soul.ts';
import { fetchVoiceSpeech } from '../web/src/ports/adapters/fetch-voice-speech.ts';
import { fetchBrowserApi } from '../web/src/ports/adapters/fetch-browser.ts';

/**
 * The `fetch` adapters of the front are tested against stand-in servers written by hand, so a route
 * renamed on the real server would pass every one of those suites. This anchors them: every call an
 * adapter makes has to be a route that exists, either in `deck/server` (its routers) or, for the
 * pass-through prefixes, in the daemon's own router source (`rinthel/rinthel_tui/api/<area>/routes.py`).
 * It checks method and path, which is where drift is silent; bodies are checked by the types of
 * `@deck/contract` and by `api-routers.test.mts`, which runs the users adapter against the real router.
 */
const DECK = path.resolve(import.meta.dirname, '..');
const DAEMON_API = path.resolve(DECK, '../rinthel/rinthel_tui/api');
const DUMMY = 'dummy-id';

function sourceFiles(dir: string, ext: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) return name === 'node_modules' || name === 'dist' || name === '__pycache__' ? [] : sourceFiles(full, ext);
    return full.endsWith(ext) ? [full] : [];
  });
}

const param = (p: string) => p.replace(/:[A-Za-z_]+|\{[a-z_]+\}/g, ':p');

/** `METHOD /api/...` for every route `deck/server` registers on a router or on the app. */
function serverRoutes(): Set<string> {
  const routes = new Set<string>();
  const re = /\b(?:router|app)\.(get|post|put|patch|delete)\(\s*["'`](\/[^"'`]*)["'`]/g;
  for (const file of sourceFiles(path.join(DECK, 'server/src'), '.ts')) {
    for (const [, method, route] of readFileSync(file, 'utf8').matchAll(re)) {
      routes.add(`${method.toUpperCase()} ${param(route.startsWith('/api') ? route : `/api${route}`)}`);
    }
  }
  return routes;
}

/** `METHOD /api/...` for every route of the daemon the Node proxy lets through, read off the daemon's FastAPI routers. */
function daemonRoutes(): Set<string> {
  const proxy = readFileSync(path.join(DECK, 'server/src/daemon-proxy.ts'), 'utf8');
  const prefixes = [...(/DAEMON_PROXY_PREFIXES[^=]*=\s*\[([^\]]*)\]/.exec(proxy)?.[1] ?? '').matchAll(/"([a-z-]+)"/g)].map((m) => m[1]);
  assert.ok(prefixes.length > 0, 'could not read the proxy prefixes');
  const routes = new Set<string>();
  for (const file of sourceFiles(DAEMON_API, '.py')) {
    for (const [, method, route] of readFileSync(file, 'utf8').matchAll(/@router\.(get|post|put|patch|delete)\(\s*"(\/[^"]*)"/g)) {
      if (prefixes.includes(route.split('/')[1])) routes.add(`${method.toUpperCase()} ${param(`/api${route}`)}`);
    }
  }
  return routes;
}

/** Calls every method of an adapter with placeholder arguments and returns the requests it made. */
async function callsOf(make: (fetchImpl: typeof fetch) => object): Promise<string[]> {
  const calls: string[] = [];
  const recording = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), 'http://deck');
    calls.push(`${init?.method ?? 'GET'} ${param(url.pathname.split('/').map((s) => (s === DUMMY ? ':p' : s)).join('/'))}`);
    return Response.json({});
  }) as typeof fetch;
  const adapter = make(recording) as Record<string, unknown>;
  for (const [, fn] of Object.entries(adapter).filter(([, v]) => typeof v === 'function')) {
    try {
      await (fn as (...a: unknown[]) => unknown)(DUMMY, DUMMY, DUMMY);
    } catch {
      // Only the request matters: the placeholder arguments are not what a real call sends.
    }
  }
  return calls;
}

const served = new Set([...serverRoutes(), ...daemonRoutes()]);

for (const [name, make, minimum] of [
  ['auth', fetchAuthApi, 3],
  ['users-admin', fetchUsersAdminApi, 4],
  // The event stream is opened as an `EventSource`; it is recorded here as the GET it is.
  ['sessions', (f: typeof fetch) => fetchSessionsApi(f, (url) => { void f(url); return { addEventListener() {}, onmessage: null, close() {} }; }), 13],
  ['models', fetchModelsApi, 4],
  ['canvases', (f: typeof fetch) => fetchCanvasesApi(f, (url) => { void f(url); return { addEventListener() {}, onmessage: null, close() {} }; }), 3],
  ['appearance', fetchAppearanceApi, 3],
  ['instance-soul', fetchInstanceSoulApi, 2],
  // Speech takes the signal of its turn, so each method is called with a live one.
  ['voice', (f: typeof fetch) => {
    const voice = fetchVoiceSpeech(f);
    const signal = new AbortController().signal;
    return { settings: () => voice.settings(), saveConfig: () => voice.saveConfig({ enabled: true }), speak: (id: string) => voice.speak(id, 'x', signal), transcribe: (id: string) => voice.transcribe(id, new Blob([]), signal) };
  }, 4],
  ['browser', fetchBrowserApi, 9],
] as const) {
  test(`every request of the ${name} adapter is a route the real server or the daemon has`, async () => {
    const calls = await callsOf(make);
    assert.ok(calls.length >= minimum, `the ${name} adapter made ${calls.length} requests, expected at least ${minimum}: a new method has to be called here too`);
    assert.deepEqual(calls.filter((c) => !served.has(c)), []);
  });
}

test('the anchor sees the routes it should: Node-owned and daemon-owned', () => {
  assert.ok(served.has('POST /api/agent/retire-sessions'));
  assert.ok(served.has('GET /api/auth/status'));
  assert.ok(served.has('PATCH /api/identity/users/:p'));
  assert.ok(served.has('GET /api/sessions/:p/events'));
  assert.ok(served.has('POST /api/models/activate'));
  assert.ok(served.has('POST /api/sessions/:p/canvases/:p/actions'));
  assert.ok(served.has('PUT /api/agent/instance-soul'));
  assert.ok(served.has('PUT /api/appearance/brand'));
  // What left with the trimmed surfaces has no route.
  for (const gone of ['GET /api/agent/legacy', 'POST /api/agent/legacy/migrate', 'GET /api/audit/guard', 'GET /api/sources']) assert.ok(!served.has(gone), gone);
  assert.ok(!served.has('GET /api/identity/groups'));
  assert.ok(!served.has('GET /api/nonexistent'));
});
