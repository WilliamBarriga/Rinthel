import express, { type Express } from "express";
import cookieParser from "cookie-parser";
import type { DaemonClient } from "./daemon-client.js";
import { requireAuth } from "./identity.js";
import { serviceCredential } from "./service-credential.js";
import type { SessionIdentity } from "./session-identity.js";
import type { PortalStore } from "./store/port.js";
import type { SessionManager } from "./session-manager.js";
import type { SessionRoots } from "./session-roots.js";
import type { SlotForgetter } from "./discard-session.js";
import type { ModelRouting } from "./model-routing/model-routing.js";
import type { Canvases } from "./canvases.js";
import type { CanvasActions } from "./canvas-actions.js";
import type { InstanceSoul } from "./instance-soul.js";
import { authRouter } from "./api/auth.js";
import { refreshSessionReader, sessionIdentityRouter } from "./api/session-identity.js";
import { userSessionsRouter } from "./api/user-sessions.js";
import { sessionsRouter } from "./api/sessions.js";
import { sessionEventsRouter } from "./api/session-events.js";
import { sessionConfigRouter } from "./api/session-config.js";
import { canvasesRouter } from "./api/canvases.js";
import { appearanceRouter } from "./api/appearance.js";
import { instanceSoulRouter } from "./api/instance-soul.js";
import { workspacesRouter } from "./api/workspaces.js";
import { modelsRouter } from "./api/models.js";
import { mountWebUi } from "./api/web-ui.js";
import { daemonProxyRouter } from "./daemon-proxy.js";

/** What the HTTP surface asks of the running Sessions (`SessionManager`, built by the composition). */
export type DeckSessions = Pick<
  SessionManager,
  "isRunning" | "stop" | "prompt" | "respondUi" | "abort" | "client" | "compact" | "on" | "off" | "liveSnapshot" | "anyGenerating"
>;

export interface DeckAppDeps {
  store: PortalStore;
  daemon: DaemonClient;
  /** Who a user is now, as the daemon says (`daemonSessionIdentity`). */
  identity: SessionIdentity;
  /** What the daemon sends as `X-Rinthel-Service-Secret`; empty closes the credential. */
  serviceSecret: string;
  /** The Sessions that run. */
  sessions: DeckSessions;
  /** Where Sessions live on Deck's volume. */
  roots: SessionRoots;
  /** The Sessions' saved slots of the local LLM, dropped with the Session. */
  slots: SlotForgetter;
  /** The daemon's route to the Local model. */
  routing: ModelRouting;
  /** The Canvases of the Sessions (the Agent writes them, the person reads them). */
  canvases: Canvases;
  /** What a click on a `ui` Canvas asks of the server: leave a message for the Agent. */
  canvasActions: CanvasActions;
  /** The SOUL every member's Sessions load. */
  instanceSoul: InstanceSoul;
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
 *  3. `requireAuth` and the live identity every later route judges by (the Session routes refresh it
 *     before their handlers);
 *  4. the routers behind the login: retire, Sessions, their events and config, their Canvases,
 *     Appearance, the Instance SOUL, workspaces, Local models, and the pass-through to the daemon
 *     last among them;
 *  5. the web UI, for every path that is not `/api`.
 */
export function createDeckApp(deps: DeckAppDeps): Express {
  const { store, daemon, identity, sessions, roots, slots, routing } = deps;
  const app = express();
  app.use(express.json({ limit: "2mb" }));
  app.use(cookieParser());

  app.use("/api", serviceCredential({ secret: deps.serviceSecret }));
  app.use("/api", authRouter({ daemon, identity }));
  app.use("/api", requireAuth(daemon));
  app.use("/api", sessionIdentityRouter(identity));
  app.use("/api", userSessionsRouter({ store, runtime: sessions, slots, roots }));
  app.use("/api", sessionsRouter({ store, runtime: sessions, slots, roots, identity }));
  app.use("/api", sessionEventsRouter({ store, runtime: sessions, allowed: (req) => refreshSessionReader(req, identity) }));
  app.use("/api", sessionConfigRouter({ store, runtime: sessions }));
  app.use("/api", canvasesRouter({ store, canvases: deps.canvases, actions: deps.canvasActions, allowed: (req) => refreshSessionReader(req, identity) }));
  app.use("/api", appearanceRouter(store.settings));
  app.use("/api", instanceSoulRouter(deps.instanceSoul));
  app.use("/api", workspacesRouter({ roots, identity }));
  app.use("/api", modelsRouter({ daemon, routing, generating: () => sessions.anyGenerating() }));
  app.use("/api", daemonProxyRouter(daemon));

  mountWebUi(app, deps.webDist);
  return app;
}
