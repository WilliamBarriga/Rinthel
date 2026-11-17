import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { cpSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

/**
 * Criterion: changing a type of the contract module (`shared/contract`) breaks the `tsc` of the
 * front and of the server. Reproducible method: the contract is copied to a temporary directory, the
 * `username` field of the daemon's identity types is renamed, and `tsc` runs over the front (and the
 * server) with an overlay `tsconfig` that points `@deck/contract` at the mutated copy. If either one
 * copied the type by hand, the mutation would not touch it and its `tsc` would pass.
 */
const DECK = path.resolve(import.meta.dirname, '..');
const TSC = path.join(DECK, 'node_modules/.bin/tsc');
const CONTRACT = path.join(DECK, 'shared/contract');

function typecheck(project: 'web' | 'server', contractDir: string, scratch: string): { ok: boolean; output: string } {
  const base = path.join(DECK, project, 'tsconfig.json');
  const config = path.join(scratch, `tsconfig.${project}.json`);
  writeFileSync(config, JSON.stringify({
    extends: base,
    compilerOptions: {
      noEmit: true, composite: false, incremental: false, declaration: false, rootDir: DECK,
      baseUrl: path.join(DECK, project),
      paths: { '@deck/contract': [path.join(contractDir, 'index.ts')] },
    },
    include: [path.join(DECK, project, 'src')],
    references: [],
  }));
  try {
    execFileSync(TSC, ['-p', config], { stdio: 'pipe', cwd: path.join(DECK, project) });
    return { ok: true, output: '' };
  } catch (e) {
    return { ok: false, output: String((e as { stdout?: Buffer }).stdout ?? e) };
  }
}

function mutated(scratch: string): string {
  const dir = path.join(scratch, 'contract');
  cpSync(CONTRACT, dir, { recursive: true });
  const file = path.join(dir, 'identity.ts');
  const text = readFileSync(file, 'utf8');
  assert.match(text, /\busername: string;/, 'the fixture field must exist');
  writeFileSync(file, text.replace(/\busername: string;/g, 'handle: string;'));
  return dir;
}

test('the front type-checks against the untouched contract', () => {
  const scratch = mkdtempSync(path.join(tmpdir(), 'contract-'));
  try {
    const r = typecheck('web', CONTRACT, scratch);
    assert.ok(r.ok, r.output);
  } finally { rmSync(scratch, { recursive: true, force: true }); }
});

test('renaming a user field in the contract breaks the front tsc', () => {
  const scratch = mkdtempSync(path.join(tmpdir(), 'contract-'));
  try {
    const r = typecheck('web', mutated(scratch), scratch);
    assert.equal(r.ok, false, 'the front still compiled: it copies the type by hand');
    assert.match(r.output, /username/);
  } finally { rmSync(scratch, { recursive: true, force: true }); }
});

test('renaming a user field in the contract breaks the server tsc', () => {
  const scratch = mkdtempSync(path.join(tmpdir(), 'contract-'));
  try {
    const r = typecheck('server', mutated(scratch), scratch);
    assert.equal(r.ok, false, 'the server still compiled: it does not use the contract');
  } finally { rmSync(scratch, { recursive: true, force: true }); }
});

test('the contract module holds only types: no runtime statements', () => {
  for (const f of ['index.ts', 'sessions.ts', 'identity.ts', 'models.ts', 'events.ts']) {
    const text = readFileSync(path.join(CONTRACT, f), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
    const stray = text.split('\n').filter((l) => /^(export\s+)?(const|let|var|function|class|enum)\b/.test(l.trim()));
    assert.deepEqual(stray, [], `${f} declares runtime values`);
  }
});
