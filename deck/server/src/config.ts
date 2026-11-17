import path from "node:path";
import type { JournalMode } from "./store/sqlite/index.js";

/** What the server reads from its environment, resolved once at boot. */
export interface DeckConfig {
  port: number;
  /** `deck.db`, on the data volume. */
  databasePath: string;
  /** `wal` unless `DECK_DB_JOURNAL_MODE=delete` (Windows bind mounts). */
  journalMode: JournalMode;
  /** Persistent place for CLIs, kept on PATH so pi and its tools can reach them. */
  binDir: string;
  /** TLS when both are set and exist, plain HTTP otherwise: `loadTls` decides. */
  tlsCertPath: string | undefined;
  tlsKeyPath: string | undefined;
  /** Signs the Panel tokens; without it Deck does not start (there is no open mode). */
  panelSecret: string;
}

export function deckConfigFromEnv(env: NodeJS.ProcessEnv): DeckConfig {
  const dataDir = path.resolve(env.DATA_DIR || "./data");
  const journal = (env.DECK_DB_JOURNAL_MODE || "wal").toLowerCase();
  if (journal !== "wal" && journal !== "delete") throw new Error(`DECK_DB_JOURNAL_MODE must be wal or delete, got "${journal}"`);
  const panelSecret = env.RINTHEL_PANEL_SECRET || "";
  if (!panelSecret) {
    throw new Error("RINTHEL_PANEL_SECRET is not set: Deck cannot validate Panel tokens. Run INSTALL on the daemon, which generates it in the root .env.");
  }
  return {
    port: Number(env.PORT || 4200),
    databasePath: path.resolve(env.DECK_DB || path.join(dataDir, "deck.db")),
    journalMode: journal,
    binDir: path.resolve(env.BIN_DIR || path.join(dataDir, "bin")),
    tlsCertPath: env.PORTAL_TLS_CERT,
    tlsKeyPath: env.PORTAL_TLS_KEY,
    panelSecret,
  };
}
