import path from "node:path";
import { fileURLToPath } from "node:url";
import { createDeckApp } from "./app.js";
import { deckConfigFromEnv } from "./config.js";
import { daemonFromEnv, serviceSecretFromEnv } from "./daemon-access.js";
import { daemonSessionIdentity } from "./daemon-session-identity.js";
import { ensureDir, gracefulShutdown, loadTls, serve } from "./startup.js";
import { openStore } from "./store/index.js";

/**
 * The server, composed: what the environment says (`config.ts`), the adapters it picks, and the
 * app over them (`app.ts`). No route is declared here.
 */
const config = deckConfigFromEnv(process.env);

// The only way to the daemon, read from the environment once.
const daemon = daemonFromEnv();

// `deck.db`, opened and migrated here, once, and handed to every router that needs it.
const store = openStore(config.databasePath, config.journalMode);

// No Session runs a pi yet: the chat brings the runtime that stops one before it is retired.
const runtime = { stop: async () => {} };

const app = createDeckApp({
  store,
  daemon,
  identity: daemonSessionIdentity(daemon),
  serviceSecret: serviceSecretFromEnv(),
  runtime,
  webDist: path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../web/dist"),
});

ensureDir(config.binDir);
const tls = loadTls(config.tlsCertPath, config.tlsKeyPath);

// Before the first request: a write left in flight by the previous server is over.
await store.canvases.interruptActiveWrites();
await store.sessions.markOrphanedInterrupted();
const server = serve(app, { port: config.port, tls }, () => {
  console.log(`deck listening on :${config.port}${tls ? " (https)" : ""}`);
  console.log(`  store:    ${config.databasePath} (${config.journalMode})`);
  console.log(`  auth:     panel token`);
});

const shutdown = gracefulShutdown({
  stop: () => store.close(),
  server,
  exit: (code) => process.exit(code),
  log: console.log,
});
process.on("SIGTERM", () => void shutdown("SIGTERM"));
process.on("SIGINT", () => void shutdown("SIGINT"));
