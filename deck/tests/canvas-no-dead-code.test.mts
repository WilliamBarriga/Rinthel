import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';

/** `web/src/canvas/` holds what a Canvas needs: a module nobody imports is dead code, and the same helper is not defined twice. */
const SRC = path.join(import.meta.dirname, '../web/src');
const walk = (dir: string): string[] => readdirSync(dir, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? walk(path.join(dir, e.name)) : [path.join(dir, e.name)]));
const isSource = (f: string) => /\.tsx?$/.test(f) && !/\.test\.tsx?$/.test(f);
const all = walk(SRC).filter(isSource);
const canvas = all.filter((f) => path.dirname(f) === path.join(SRC, 'canvas'));

test('every module of canvas/ is imported by another module of the web app', () => {
  const dead = canvas.filter((file) => {
    const base = path.basename(file).replace(/\.tsx?$/, '');
    const imported = new RegExp(`from ['"][^'"]*/${base}['"]`);
    return !all.some((other) => other !== file && imported.test(readFileSync(other, 'utf8')));
  });
  assert.deepEqual(dead.map((f) => path.basename(f)), []);
});

test('canvas/ does not redefine messageOf: it comes from the ports', () => {
  const own = canvas.filter((f) => /(const|function) messageOf\b/.test(readFileSync(f, 'utf8')));
  assert.deepEqual(own.map((f) => path.basename(f)), []);
});
