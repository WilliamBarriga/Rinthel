import express, { type Express } from "express";
import cookieParser from "cookie-parser";
import type { DaemonClient } from "./daemon-client.js";
import { requireAuth } from "./identity.js";
import { serviceCredential } from "./service-credential.js";
import type { SessionIdentity } from "./session-identity.js";
import type { PortalStore } from "./store/port.js";
import { authRouter } from "./api/auth.js";
import { sessionIdentityRouter } from "./api/session-identity.js";
import { userSessionsRouter, type SessionRuntime } from "./api/user-sessions.js";
import { mountWebUi } from "./api/web-ui.js";
import { daemonProxyRouter } from "./daemon-proxy.js";

export interface DeckAppDeps {
  store: PortalStore;
  daemon: DaemonClient;
  /** Who a user is now, as the daemon says (`daemonSessionIdentity`). */
  identity: SessionIdentity;
  /** What the daemon sends as `X-Rinthel-Service-Secret`; empty closes the credential. */
  serviceSecret: string;
  /** The Sessions that run, stopped before they are retired. */
  runtime: SessionRuntime;
  /** The built web UI; without it the server is an API only. */
  webDist: string;
}

/**
 * The HTTP surface of Deck, composed from the adapters it is given: `index.ts` passes the real ones
 * and the tests pass doubles. No route is declared here; each one lives under `api/` (or in
 * `daemon-proxy.ts`), mounted in this order:
 *
 *  1. the daemon's service credential, which judges alone any request carrying its header;
 *  2. login, logout and status, before the login is required;
 *  3. `requireAuth` and the live identity every later route judges by;
 *  4. the routers behind the login; the pass-through to the daemon last among them;
 *  5. the web UI, for every path that is not `/api`.
 *
 * The chat (Sessions, events, the model proxy) mounts its routers in step 4 when it arrives.
 */
export function createDeckApp(deps: DeckAppDeps): Express {
  const { store, daemon, identity } = deps;
  const app = express();
  app.use(express.json({ limit: "2mb" }));
  app.use(cookieParser());

  app.use("/api", serviceCredential({ secret: deps.serviceSecret }));
  app.use("/api", authRouter({ daemon, identity }));
  app.use("/api", requireAuth(daemon));
  app.use("/api", sessionIdentityRouter(identity));
  app.use("/api", userSessionsRouter({ store, runtime: deps.runtime }));
  app.use("/api", daemonProxyRouter(daemon));

  mountWebUi(app, deps.webDist);
  return app;
}
