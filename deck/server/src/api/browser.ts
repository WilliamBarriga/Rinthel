import express, { type Router } from "express";
import { randomBytes } from "node:crypto";
import type { BrowserStatus } from "@deck/contract";
import type { PortalStore } from "../store/port.js";
import type { BrowserSettings } from "../browser-settings.js";
import type { BrowserRuntime } from "../instance-browser.js";
import { adminOnly } from "./admin-only.js";
import { cdpOverHttp } from "../browser/cdp.js";

/** What the Instance browser's refusals name (`adminOnly`, and the `/browser-ui` proxy). */
export const INSTANCE_BROWSER = "el browser de la Instance";

/** What the browser's routes reach: Deck's store, the browser's saved settings, its lifecycle and its CDP endpoint. */
export interface BrowserDeps {
  store: PortalStore;
  settings: BrowserSettings;
  runtime: BrowserRuntime;
  /** The Instance browser's fixed CDP endpoint. */
  cdpUrl: string;
}

/**
 * The Instance browser: whether it is up, its lifecycle and config, the allowlist, and which Sessions
 * may drive it. Admin only, reading included: the browser holds the Agent's live logins, so anyone
 * else gets a `403` and does not see it (the web hides it on that answer). The browser runs in its
 * own container (or a Chrome of the machine) with a profile that stays signed in; Deck owns the
 * question of which Sessions may reach it.
 */
export function browserRouter({ store, settings, runtime, cdpUrl }: BrowserDeps): Router {
  const router = express.Router();
  const cdp = cdpOverHttp(cdpUrl);
  router.use("/browser", adminOnly(INSTANCE_BROWSER));
  router.use("/sessions/:id/browser", adminOnly(INSTANCE_BROWSER));

  router.get("/browser", async (_req, res) => {
    // Not running is a normal state, not an error: the browser is optional.
    const version = await cdp.version();
    const pages = version === null ? [] : await cdp.pages();
    const config = await settings.config();
    const sessions = await store.sessions.listBrowserEnabled();
    const body: BrowserStatus = {
      running: Boolean(version),
      // An unauthenticated browser holding live logins is the worst outcome here, and nothing else would tell.
      unprotected: Boolean(version) && !config.password,
      version,
      pages,
      uiPort: config.httpsPort,
      allowlist: (await settings.allowlist()).join("\n"),
      // A socket Deck may not use (no docker group) is said, not a 500: the rest of the status still reads.
      install: await runtime.status().catch((e: Error) => ({
        available: false,
        mode: "docker" as const,
        image: false,
        container: "unavailable" as const,
        pulling: { active: false, line: "", error: e.message },
      })),
      config: { user: config.user, hasPassword: Boolean(config.password) },
      sessions: sessions.map((s) => ({ id: s.id, title: s.title, kind: s.kind })),
    };
    res.json(body);
  });

  const lifecycle = (fn: (req: express.Request) => Promise<void>) => async (req: express.Request, res: express.Response) => {
    try {
      await fn(req);
      res.json({ ok: true });
    } catch (e) {
      res.status(400).json({ error: (e as Error).message });
    }
  };
  /** Installs with the saved config: the password is checked by the runtime, where it matters. */
  router.post("/browser/install", lifecycle(async () => runtime.install(await settings.config())));
  router.post("/browser/start", lifecycle(() => runtime.start()));
  router.post("/browser/stop", lifecycle(() => runtime.stop()));
  /** Removes the container. `?profile=forget` also drops the logins. */
  router.delete("/browser/install", lifecycle((req) => (req.query.profile === "forget" ? runtime.forgetProfile() : runtime.remove())));

  router.put("/browser/config", async (req, res) => {
    const { user, password, port, httpsPort } = req.body ?? {};
    const saved = await settings.save({ user, password, port, httpsPort });
    res.json({ user: saved.user, hasPassword: Boolean(saved.password) });
  });

  router.get("/browser/suggest-password", (_req, res) => {
    res.json({ password: randomBytes(12).toString("hex") });
  });

  /** Domains the browser may be pointed at, one per line. Empty means no restriction. */
  router.put("/browser/allowlist", async (req, res) => {
    const domains = req.body?.domains;
    if (typeof domains !== "string") return void res.status(400).json({ error: "domains required" });
    await settings.setAllowlist(domains);
    res.json({ allowlist: (await settings.allowlist()).join("\n") });
  });

  /**
   * Turns the browser on or off for one Session. The gate reads it at each call, so it applies now;
   * a miembro's Session never drives the browser whatever this says (its owner is not an admin).
   */
  router.put("/sessions/:id/browser", async (req, res) => {
    const on = Boolean(req.body?.enabled);
    const row = await store.sessions.get(req.params.id);
    if (!row) return void res.status(404).json({ error: "Not found" });
    await store.sessions.setBrowser(row.id, on);
    res.json({ enabled: on });
  });

  return router;
}
