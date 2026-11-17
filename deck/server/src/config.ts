import path from "node:path";
import type { JournalMode } from "./store/sqlite/index.js";
import type { HostExecAccess } from "./pi/host-exec/host-exec-tools.js";

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
  /** Deck's volume: Sessions' pi files, each owner's Agent home and workspaces. */
  dataDir: string;
  /** The Instance SOUL, where INSTALL seeds it: `<data>/instance/SOUL.md`. */
  instanceSoulFile: string;
  /** The Instance's workspaces, the admin's (`WORKSPACE_ROOT`). */
  workspaceRoot: string;
  /** llama-server's `--slot-save-path`, as this process sees it. */
  slotsDir: string;
  /** What the saved slots may hold in all (`DECK_SLOTS_MAX_GB`, 20 by default). */
  slotsMaxBytes: number;
  /**
   * hostexecd, as the daemon hands it (`RINTHEL_HOSTEXECD_URL`, `RINTHEL_HOSTEXECD_TOKEN`): set only
   * with a token. Without one, no Session has the host exec tools; the URL is checked when they register.
   */
  hostExec: HostExecAccess | undefined;
}

export function deckConfigFromEnv(env: NodeJS.ProcessEnv): DeckConfig {
  const dataDir = path.resolve(env.DATA_DIR || "./data");
  const journal = (env.DECK_DB_JOURNAL_MODE || "wal").toLowerCase();
  if (journal !== "wal" && journal !== "delete") throw new Error(`DECK_DB_JOURNAL_MODE must be wal or delete, got "${journal}"`);
  const panelSecret = env.RINTHEL_PANEL_SECRET || "";
  if (!panelSecret) {
    throw new Error("RINTHEL_PANEL_SECRET is not set: Deck cannot validate Panel tokens. Run INSTALL on the daemon, which generates it in the root .env.");
  }
  const hostExecToken = (env.RINTHEL_HOSTEXECD_TOKEN || "").trim();
  const slotsGb = Number(env.DECK_SLOTS_MAX_GB || 20);
  if (!Number.isFinite(slotsGb) || slotsGb <= 0) throw new Error(`DECK_SLOTS_MAX_GB must be a positive number, got "${env.DECK_SLOTS_MAX_GB}"`);
  return {
    port: Number(env.PORT || 4100),
    databasePath: path.resolve(env.DECK_DB || path.join(dataDir, "deck.db")),
    journalMode: journal,
    binDir: path.resolve(env.BIN_DIR || path.join(dataDir, "bin")),
    tlsCertPath: env.PORTAL_TLS_CERT,
    tlsKeyPath: env.PORTAL_TLS_KEY,
    panelSecret,
    dataDir,
    instanceSoulFile: path.join(dataDir, "instance", "SOUL.md"),
    workspaceRoot: path.resolve(env.WORKSPACE_ROOT || path.join(dataDir, "workspaces")),
    slotsDir: path.resolve(env.DECK_SLOTS_DIR || path.join(dataDir, "llama-slots")),
    slotsMaxBytes: Math.floor(slotsGb * 1024 ** 3),
    hostExec: hostExecToken ? { url: (env.RINTHEL_HOSTEXECD_URL || "").trim(), token: hostExecToken } : undefined,
  };
}
