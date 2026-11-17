import path from "node:path";
import { fileURLToPath } from "node:url";
import { createCanvasActions, storedSessionNotes } from "./canvas-actions.js";
import { createCanvases } from "./canvases.js";
import { createDeckApp } from "./app.js";
import { deckConfigFromEnv } from "./config.js";
import { daemonFromEnv, serviceSecretFromEnv } from "./daemon-access.js";
import { daemonSessionIdentity } from "./daemon-session-identity.js";
import { FsInstanceSoul } from "./instance-soul-fs.js";
import { startEventRetention, eventRetentionDays } from "./event-retention.js";
import { DaemonModelRouting } from "./model-routing/daemon-model-routing.js";
import { SdkPiClient } from "./pi/sdk-client.js";
import { SessionManager } from "./session-manager.js";
import { SessionProxy } from "./session-proxy.js";
import { FsSessionRoots } from "./session-roots-fs.js";
import { LlamaSlotStore } from "./session-slots/llama-slot-store.js";
import { SessionSlots } from "./session-slots/session-slots.js";
import { ensureDir, gracefulShutdown, loadTls, serve } from "./startup.js";
import { openStore } from "./store/index.js";
import { browserSettings } from "./browser-settings.js";
import { attachBrowserUpgrade } from "./browser-proxy.js";
import { createBrowserRuntime } from "./extensions/browser-runtime.js";
import { dockerOverSocket } from "./extensions/docker.js";
import { CHROME_CANDIDATES, LocalChrome } from "./extensions/browser-local.js";
import { watchBrowserFrames } from "./extensions/browser-frames.js";
import { McpStdioBrowserDriver } from "./extensions/mcp-stdio-browser-driver.js";

/**
 * The server, composed: what the environment says (`config.ts`), the adapters it picks, and the
 * app over them (`app.ts`). No route is declared here.
 */
const config = deckConfigFromEnv(process.env);

// The only way to the daemon, read from the environment once.
const daemon = daemonFromEnv();

// `deck.db`, opened and migrated here, once, and handed to every router that needs it.
const store = openStore(config.databasePath, config.journalMode);
const identity = daemonSessionIdentity(daemon);

// The Local model: the daemon's route, straight to llama-server, each Session's slot kept on Deck's volume.
const routing = new DaemonModelRouting(daemon);
const slots = new SessionSlots(new LlamaSlotStore(config.slotsDir), { maxBytes: config.slotsMaxBytes });
const roots = new FsSessionRoots(config.dataDir, config.workspaceRoot);

// What the Agent writes for the person (Canvases) and what every member's Agent is told it is.
const canvases = createCanvases(store);
const canvasActions = createCanvasActions({ canvases, notes: storedSessionNotes(store) });
const instanceSoul = new FsInstanceSoul(config.instanceSoulFile);

// The Instance browser: one per Instance, installed, started and stopped by an admin, never stopped
// for being idle. Every admin Session that may drive it shares it over its fixed CDP endpoint.
const browserConfig = config.browser;
const browserStore = browserSettings(store.settings, browserConfig.defaults);
const browserRuntime = createBrowserRuntime({
  external: browserConfig.external,
  cdpUrl: browserConfig.cdpUrl,
  docker: dockerOverSocket(browserConfig.dockerSocket),
  local: new LocalChrome({
    candidates: [...(browserConfig.binary ? [browserConfig.binary] : []), ...CHROME_CANDIDATES],
    profileDir: browserConfig.localProfileDir,
    display: process.env.DISPLAY,
    searchPath: process.env.PATH,
  }),
  volume: browserConfig.volume,
  timezone: process.env.TZ,
});
// The Agent's browser tools: Playwright's MCP server over the CDP endpoint, one process for every Session.
const [mcpCommand, ...mcpArgs] = browserConfig.mcpCommand;
const browserDriver = new McpStdioBrowserDriver({
  command: mcpCommand,
  // Snapshots on demand: a whole page is not repeated after every click or keystroke.
  args: (endpoint) => [...mcpArgs, "--cdp-endpoint", endpoint, "--snapshot-mode", "none"],
  // The catalogue is listed by a throwaway server with no browser behind it.
  probeArgs: () => [...mcpArgs, "--snapshot-mode", "none"],
  callTimeoutMs: 120_000,
});
// Keeps the browser rendering when nobody has its view open.
const browserViewers = watchBrowserFrames(browserRuntime, browserConfig.streamPort);

let sessions: SessionManager;
const proxy = new SessionProxy({
  routing,
  slots,
  // How far llama-server has got through a prompt, which is otherwise a silent minute before the first token.
  onProgress: (sessionId, prefill) => sessions.reportPrefill(sessionId, prefill),
  onRoute: (sessionId, route) => sessions.reportRoute(sessionId, route),
});
sessions = new SessionManager({
  store,
  identity,
  proxy,
  roots,
  canvases,
  instanceSoulFile: instanceSoul.path,
  launch: (opts) => SdkPiClient.create(opts),
  browser: { driver: browserDriver, cdpEndpoint: browserConfig.cdpUrl, allowlist: () => browserStore.allowlist() },
});

const app = createDeckApp({
  store,
  daemon,
  identity,
  serviceSecret: serviceSecretFromEnv(),
  sessions,
  roots,
  slots,
  routing,
  canvases,
  canvasActions,
  instanceSoul,
  webDist: path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../web/dist"),
  browser: { settings: browserStore, runtime: browserRuntime, cdpUrl: browserConfig.cdpUrl, uiHost: browserConfig.uiHost, viewers: browserViewers },
});

ensureDir(config.binDir);
ensureDir(config.slotsDir);
const tls = loadTls(config.tlsCertPath, config.tlsKeyPath);

await proxy.start();
startEventRetention(store, eventRetentionDays(process.env));
// Before the first request: a write left in flight by the previous server is over.
await store.canvases.interruptActiveWrites();
await store.sessions.markOrphanedInterrupted();
const server = serve(app, { port: config.port, tls }, () => {
  console.log(`deck listening on :${config.port}${tls ? " (https)" : ""}`);
  console.log(`  store:      ${config.databasePath} (${config.journalMode})`);
  console.log(`  workspaces: ${config.workspaceRoot}`);
  console.log(`  slots:      ${config.slotsDir}`);
  console.log(`  auth:       panel token`);
  console.log(`  browser:    ${browserConfig.external ? "external" : "docker or local"} at ${browserConfig.cdpUrl}`);
});
// The Instance browser's view streams over a websocket: the upgrade needs the server, not the app.
attachBrowserUpgrade(server, { settings: browserStore, identity, host: browserConfig.uiHost, viewers: browserViewers });

const shutdown = gracefulShutdown({
  stop: async () => {
    await sessions.shutdown();
    browserViewers.stop();
    browserDriver.close();
    proxy.stop();
    await store.close();
  },
  server,
  exit: (code) => process.exit(code),
  log: console.log,
});
process.on("SIGTERM", () => void shutdown("SIGTERM"));
process.on("SIGINT", () => void shutdown("SIGINT"));
