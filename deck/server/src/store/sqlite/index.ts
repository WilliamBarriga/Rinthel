import Database from "better-sqlite3";
import type { PortalStore } from "../port.js";
import { sqliteCanvases } from "./canvases.js";
import { MIGRATIONS, SCHEMA_VERSION } from "./schema.js";
import { sqliteSessions } from "./sessions.js";
import { sqliteSessionTaint } from "./session-taint.js";
import { sqliteSettings } from "./settings.js";

export { SCHEMA_VERSION } from "./schema.js";

/** `wal` by default; `delete` where WAL cannot work (a Windows bind mount into the container). */
export type JournalMode = "wal" | "delete";

export interface SqliteStoreOptions {
  journalMode?: JournalMode;
  /** The clock of the event log; tests inject one. */
  now?: () => Date;
}

/** STRICT tables arrived in SQLite 3.37: an older library does not open the store. */
export function requireSqliteVersion(version: string): void {
  const [major, minor] = version.split(".").map(Number);
  if (major < 3 || (major === 3 && minor < 37)) {
    throw new Error(`SQLite ${version} is too old for deck.db: 3.37 or newer is required`);
  }
}

/** Brings the file to `SCHEMA_VERSION`, each migration in its own transaction; a newer file is refused. */
function migrate(db: Database.Database, file: string): void {
  const current = db.pragma("user_version", { simple: true }) as number;
  if (current > SCHEMA_VERSION) {
    throw new Error(`${file} is at schema version ${current}, newer than this Deck knows (${SCHEMA_VERSION}): update Deck`);
  }
  for (let version = current; version < SCHEMA_VERSION; version++) {
    db.transaction(() => {
      db.exec(MIGRATIONS[version]);
      db.pragma(`user_version = ${version + 1}`);
    }).immediate();
  }
}

/**
 * Opens `deck.db` (one synchronous connection for the one Deck process), migrates it and returns
 * the portal store over it. Whoever opens the store closes it (`store.close()`). Throws, and the
 * server does not start, on an old SQLite or a file newer than this code.
 */
export function openSqliteStore(file: string, options: SqliteStoreOptions = {}): PortalStore {
  const db = new Database(file);
  try {
    requireSqliteVersion((db.prepare("SELECT sqlite_version() AS v").get() as { v: string }).v);
    db.pragma(`journal_mode = ${options.journalMode ?? "wal"}`);
    db.pragma("foreign_keys = ON");
    db.pragma("busy_timeout = 5000");
    migrate(db, file);
  } catch (e) {
    db.close();
    throw e;
  }
  return {
    sessions: sqliteSessions(db, options.now),
    canvases: sqliteCanvases(db),
    settings: sqliteSettings(db),
    sessionTaint: sqliteSessionTaint(db),
    async close() {
      if (db.open) db.close();
    },
  };
}
