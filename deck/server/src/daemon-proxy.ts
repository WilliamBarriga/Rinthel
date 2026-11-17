import express, { type Router } from "express";
import { accessTokenOf } from "./identity.js";
import type { DaemonClient } from "./daemon-client.js";
import { adminOnly } from "./api/admin-only.js";

/**
 * Pass-through to the daemon for the data it owns. The browser only talks to Node; for these
 * prefixes Node owns no logic: it forwards the request with the Panel token `requireAuth` already
 * validated (and refreshed) as Bearer, and returns the daemon's status and body (only
 * `content-type` and the security headers are forwarded), so a `401` means "invalid session" and an
 * unreachable daemon is `502`.
 *
 * Daemon route names, in English as the daemon declares them: usuarios (admin only) -> identity/users.
 *
 * Anything outside this list is not matched here and falls through, so it is a 404 unless another
 * router owns it. Login, refresh and logout manage cookies and stay on their own routes, mounted
 * before this router.
 */
export const DAEMON_PROXY_PREFIXES: readonly string[] = ["identity"];

/** What the browser may reach under `/identity`: the users, by id. */
const IDENTITY_RELAYABLE = /^\/identity\/users(\/\d+)?$/;

const BODYLESS = new Set(["GET", "HEAD", "DELETE", "OPTIONS"]);

export function daemonProxyRouter(daemon: DaemonClient): Router {
  const router = express.Router();
  // Users are the admin's; the daemon checks again (policy `admin`).
  const adminIdentity = adminOnly("los usuarios");
  router.use((req, res, next) => (IDENTITY_RELAYABLE.test(req.url.split("?")[0]) ? adminIdentity(req, res, next) : next()));
  router.use(async (req, res, next) => {
    const path = req.url.split("?")[0];
    if (!DAEMON_PROXY_PREFIXES.includes(path.split("/")[1]) || !IDENTITY_RELAYABLE.test(path)) return next();
    const token = accessTokenOf(req);
    if (!token) {
      res.status(401).json({ error: "Unauthorized" });
      return;
    }
    const init: RequestInit = { method: req.method };
    if (!BODYLESS.has(req.method) && req.body && Object.keys(req.body).length > 0) {
      init.headers = { "content-type": "application/json" };
      init.body = JSON.stringify(req.body);
    }
    try {
      const upstream = await daemon.withPanelToken(token).fetch(req.url, init);
      const body = Buffer.from(await upstream.arrayBuffer());
      res.status(upstream.status).set("content-type", upstream.headers.get("content-type") ?? "application/json");
      for (const name of ["x-content-type-options", "cache-control", "content-security-policy"]) {
        const value = upstream.headers.get(name);
        if (value) res.set(name, value);
      }
      res.send(body);
    } catch (e) {
      res.status(502).json({ error: (e as Error).message });
    }
  });
  return router;
}
