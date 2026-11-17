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
  /** The Instance browser. */
  browser: InstanceBrowserConfig;
  /**
   * hostexecd, as the daemon hands it (`RINTHEL_HOSTEXECD_URL`, `RINTHEL_HOSTEXECD_TOKEN`): set only
   * with a token. Without one, no Session has the host exec tools; the URL is checked when they register.
   */
  hostExec: HostExecAccess | undefined;
  /**
   * Understory's token (`UNDERSTORY_TOKEN`, the root `.env`'s): set, an admin's Sessions get Memoria;
   * unset or blank, no Session has it. The URL is the daemon's, read on each call.
   */
  understoryToken: string | undefined;
}

/**
 * Pinned, not `@latest`: the tool signatures changed underneath a working setup once (click and type
 * took `{element, ref}`, then `{target}`), and a browser the Agent depends on is no place for a silent
 * upgrade.
 */
export const PLAYWRIGHT_MCP = "@playwright/mcp@0.0.79";

export interface InstanceBrowserConfig {
  /** Its fixed CDP endpoint (`BROWSER_CDP_URL`). */
  cdpUrl: string;
  /** Started and stopped outside Deck (`BROWSER_EXTERNAL=true`); otherwise docker, or a local Chrome without a socket. */
  external: boolean;
  /** The Playwright MCP server that drives it over CDP, as argv (`BROWSER_MCP_COMMAND`). */
  mcpCommand: string[];
  dockerSocket: string;
  /** The container's profile volume: its logins (`BROWSER_VOLUME`). */
  volume: string;
  /** A local Chrome's profile, on the data volume. */
  localProfileDir: string;
  /** Tried first for a local Chrome (`BROWSER_BINARY`). */
  binary: string | undefined;
  /** Where its view listens (`BROWSER_HOST`). */
  uiHost: string;
  /** selkies' stream websocket, kept watched so the page keeps rendering (`BROWSER_STREAM_PORT`). */
  streamPort: number;
  /** The login and ports of the view, before the admin saves their own. */
  defaults: { user?: string; password?: string; port?: string; httpsPort?: string };
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
  const understoryToken = (env.UNDERSTORY_TOKEN || "").trim();
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
    browser: {
      cdpUrl: env.BROWSER_CDP_URL || "http://127.0.0.1:9222",
      external: env.BROWSER_EXTERNAL === "true",
      mcpCommand: (env.BROWSER_MCP_COMMAND || `npx -y ${PLAYWRIGHT_MCP}`).trim().split(/\s+/),
      dockerSocket: env.DOCKER_SOCKET || "/var/run/docker.sock",
      volume: env.BROWSER_VOLUME || "deck_browser-profile",
      localProfileDir: path.join(dataDir, "browser-profile"),
      binary: env.BROWSER_BINARY || undefined,
      uiHost: env.BROWSER_HOST || "127.0.0.1",
      streamPort: Number(env.BROWSER_STREAM_PORT || 8082),
      defaults: { user: env.BROWSER_USER, password: env.BROWSER_PASSWORD, port: env.BROWSER_PORT, httpsPort: env.BROWSER_HTTPS_PORT },
    },
    hostExec: hostExecToken ? { url: (env.RINTHEL_HOSTEXECD_URL || "").trim(), token: hostExecToken } : undefined,
    understoryToken: understoryToken || undefined,
  };
}
