import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { join, relative } from 'node:path';

/** Every file under `dir` that is source or config a reader of the env could live in. */
function files(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap(entry => {
    if (['node_modules', 'dist', 'test-results'].includes(entry.name)) return [];
    const path = join(dir, entry.name);
    return entry.isDirectory() ? files(path) : /\.(ts|tsx|mts|mjs|js)$/.test(entry.name) ? [path] : [];
  });
}

test('only daemonFromEnv reads RINTHEL_DAEMON_URL', () => {
  const deck = new URL('..', import.meta.url).pathname;
  const readers = files(join(deck, 'server', 'src'))
    .concat(files(join(deck, 'web')))
    .filter(path => readFileSync(path, 'utf8').includes('RINTHEL_DAEMON_URL'))
    .map(path => relative(deck, path));

  assert.deepEqual(readers, ['server/src/daemon-access.ts']);
});
