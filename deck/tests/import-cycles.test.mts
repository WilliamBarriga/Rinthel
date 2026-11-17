import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { importCycles } from './helpers/import-graph.mts';

// The server's runtime import graph (from index.ts) has no cycle at all.
// A module that needs a collaborator takes it as a parameter instead of importing it back.
test('the server has no import cycle', () => {
  assert.deepEqual(importCycles().map((c) => c.join(' -> ')), []);
});

test('the store singleton is gone: no source under server/src defines or calls getStore', () => {
  const src = path.resolve(import.meta.dirname, '../server/src');
  const found = (readdirSync(src, { recursive: true }) as string[])
    .filter((f) => f.endsWith('.ts'))
    .filter((f) => /\bgetStore\b/.test(readFileSync(path.join(src, f), 'utf8')));
  assert.deepEqual(found, []);
});
