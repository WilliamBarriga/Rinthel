import test, { after } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import Database from "better-sqlite3";
import { openSqliteStore, SCHEMA_VERSION, requireSqliteVersion } from "../dist/store/sqlite/index.js";

// The migrator of `deck.db`: it runs when the store opens, keyed on `PRAGMA user_version`.
const dir = mkdtempSync(path.join(tmpdir(), "deck-migrate-"));
after(() => rmSync(dir, { recursive: true, force: true }));
let n = 0;
const file = () => path.join(dir, `deck-${n++}.db`);
const pragma = (f, name) => {
  const db = new Database(f, { readonly: true });
  try { return db.pragma(name, { simple: true }); } finally { db.close(); }
};

test("a new file is migrated to the version this code knows, with STRICT tables", async () => {
  const f = file();
  const store = openSqliteStore(f);
  await store.close();
  assert.equal(pragma(f, "user_version"), SCHEMA_VERSION);
  const db = new Database(f, { readonly: true });
  try {
    const tables = db.prepare("SELECT name, strict FROM pragma_table_list WHERE schema = 'main' AND name NOT LIKE 'sqlite_%' ORDER BY name").all();
    assert.deepEqual(tables, ["canvases", "events", "notes", "sessions", "settings"].map((name) => ({ name, strict: 1 })));
  } finally { db.close(); }
});

test("opening again keeps what is stored: the migration runs once", async () => {
  const f = file();
  const first = openSqliteStore(f);
  await first.settings.set("k", "v");
  await first.close();
  const again = openSqliteStore(f);
  assert.deepEqual(await again.settings.all(), { k: "v" });
  await again.close();
});

test("a file at a newer version than this code knows does not open", () => {
  const f = file();
  const db = new Database(f);
  db.pragma(`user_version = ${SCHEMA_VERSION + 1}`);
  db.close();
  assert.throws(() => openSqliteStore(f), /newer/);
});

test("WAL by default, DELETE when asked (Windows bind mounts)", async () => {
  const wal = file();
  await openSqliteStore(wal).close();
  assert.equal(pragma(wal, "journal_mode"), "wal");

  const del = file();
  await openSqliteStore(del, { journalMode: "delete" }).close();
  assert.equal(pragma(del, "journal_mode"), "delete");
});

test("SQLite older than 3.37 is refused: STRICT tables need it", () => {
  assert.throws(() => requireSqliteVersion("3.36.9"), /3\.37/);
  assert.doesNotThrow(() => requireSqliteVersion("3.37.0"));
  assert.doesNotThrow(() => requireSqliteVersion("3.54.1"));
});
