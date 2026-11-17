import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { ALLOWED, ADAPTERS, domainFiles, isAdapter, violationsIn, domainViolations } from './helpers/domain-imports.mts';

const SRC = path.resolve(import.meta.dirname, '../server/src');
const DOMAIN = domainFiles();

// The import guard of Node's domain (ADR 0004), cousin of rinthel/tests/test_import_table.py
// (table in rinthel/tests/import_table.py). The domains of server/src do not import
// infrastructure: fs, child_process, network, better-sqlite3, express, the global `fetch` nor
// `process.env`. What they need from outside comes in through a port or a parameter.

const probe = (source: string) => violationsIn('probe.ts', source, new Set(['probe.ts', 'other.ts']));

test('a forbidden import makes the guard fail', () => {
  assert.deepEqual(probe(`import { readFileSync } from "node:fs";`), ['node:fs']);
  assert.deepEqual(probe(`import { spawn } from 'child_process';`), ['child_process']);
  assert.deepEqual(probe(`import Database from "better-sqlite3";`), ['better-sqlite3']);
  assert.deepEqual(probe(`import express from "express";`), ['express']);
  assert.deepEqual(probe(`const m = await import("node:fs/promises");`), ['node:fs/promises']);
  assert.deepEqual(probe(`export { x } from "node:http";`), ['node:http']);
});

test('the global fetch and process.env count as infrastructure; a method named fetch does not', () => {
  assert.deepEqual(probe(`const r = await fetch(url);`), ['fetch()']);
  assert.deepEqual(probe(`const r = await globalThis.fetch(url);`), ['globalThis.fetch']);
  assert.deepEqual(probe(`const d = process.env.HOME;`), ['process.env']);
  assert.deepEqual(probe(`const r = await daemon.fetch("/x");`), []);
});

test('a domain may import pure packages, node built-ins without I/O, and other domain modules', () => {
  assert.deepEqual(probe(`import { nanoid } from "nanoid"; import { EventEmitter } from "node:events"; import { randomBytes } from "node:crypto";`), []);
  assert.deepEqual(probe(`import { a } from "./other.js"; import type { T } from "./not-domain.js";`), []);
});

test('a domain does not import a module outside the domain set (an adapter)', () => {
  assert.deepEqual(probe(`import { openSqliteStore } from "./store/sqlite/index.js";`), ['./store/sqlite/index.js']);
});

test('the current tree passes: no domain imports infrastructure', () => {
  assert.deepEqual(domainViolations(), {});
});

test('every domain file exists, and every ALLOWED entry is still needed', () => {
  assert.deepEqual(DOMAIN.filter((f) => !existsSync(path.join(SRC, f))), []);
  const domain = new Set(DOMAIN);
  const stale = Object.entries(ALLOWED).flatMap(([file, entries]) => {
    const found = domain.has(file) ? violationsIn(file, readFileSync(path.join(SRC, file), 'utf8'), domain) : [];
    return Object.keys(entries).filter((e) => !found.includes(e)).map((e) => `${file}: ${e}`);
  });
  assert.deepEqual(stale, []);
});

test('the guard reads the syntax tree: text that looks like an import or a comment is not one', () => {
  assert.deepEqual(probe(`const t = "import fs from 'node:fs'"; const u = "http://x";`), []);
  assert.deepEqual(probe("const t = `from \"pg\"`;"), []);
  assert.deepEqual(probe(`const s = "a // b"; import fs from "node:fs";`), ['node:fs']);
  assert.deepEqual(probe(`// import fs from "node:fs";\n/* fetch(url) */ const x = 1;`), []);
});

test('a module is domain by default; only the listed adapters and composition stay outside', () => {
  assert.ok(!isAdapter('brand-new.ts'));
  assert.ok(!isAdapter('pi/another-tool.ts'));
  for (const f of ['store/sqlite/sessions.ts', 'store/memory/state.ts', 'api/auth.ts', 'index.ts', 'app.ts', 'daemon-session-identity.ts'])
    assert.ok(isAdapter(f), f);
});

test('the domain covers the ports the stack added', () => {
  for (const f of ['session-identity.ts', 'store/port.ts', 'discard-session.ts', 'config.ts'])
    assert.ok(DOMAIN.includes(f), f);
  assert.ok(!DOMAIN.some(isAdapter));
});

test('no domain file reads process.env; the entry point passes the config in', () => {
  assert.deepEqual(Object.entries(ALLOWED).filter(([, a]) => 'process.env' in a).map(([f]) => f), []);
});

test('every adapter entry still matches a file', () => {
  const all = domainFiles({ includeAdapters: true });
  assert.deepEqual(ADAPTERS.filter((a) => !all.some((f) => f === a || (a.endsWith('/') && f.startsWith(a)))), []);
});
