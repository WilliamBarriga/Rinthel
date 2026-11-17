import { mkdirSync } from "node:fs";
import path from "node:path";
import type { PortalStore } from "./port.js";
import { openSqliteStore, type JournalMode } from "./sqlite/index.js";

export type { PortalStore } from "./port.js";

/**
 * Opens the portal's store on `deck.db` and migrates it. The composition root calls it once and
 * hands the store to whoever needs it; whoever opens a store closes it (`store.close()`). Throws on
 * an old SQLite or a file at a newer version than this code, so the server refuses to start.
 */
export function openStore(databasePath: string, journalMode: JournalMode): PortalStore {
  mkdirSync(path.dirname(databasePath), { recursive: true });
  return openSqliteStore(databasePath, { journalMode });
}
