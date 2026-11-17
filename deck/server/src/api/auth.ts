import express, { type Router } from "express";
import type { DaemonClient } from "../daemon-client.js";
import {
  revokeLogin,
  clearSessionCookies,
  issueCookiesFor,
  login,
  logout,
  refreshTokenOf,
  claimsOfRequest,
} from "../identity.js";
import { IDENTITY_REFUSAL, readIdentity, type SessionIdentity } from "../session-identity.js";

/**
 * Login, logout and who is asking: the routes that answer before `requireAuth`.
 * The people and their passwords are the daemon's; Deck only holds the Panel token.
 *
 * `identity` is who the caller is now, the source `adminOnly` judges by: `/auth/status` reports that role rather than
 * the one in an access token that is still valid, so a demoted admin reads `miembro` on the next check, a disabled or
 * deleted user is not authenticated, and an identity that cannot be read is a `502` (never an admin). A login is
 * always required: `authRequired` is always `true`.
 */
export function authRouter({ daemon, identity }: { daemon: DaemonClient; identity: SessionIdentity }): Router {
  const router = express.Router();

  router.get("/auth/status", async (req, res) => {
    const claims = claimsOfRequest(req);
    if (!claims) return void res.json({ authRequired: true, authed: false });
    const read = await readIdentity(() => identity.current(claims.userId));
    if (read.access !== 200) {
      if (read.access === 502) return void res.status(502).json({ error: IDENTITY_REFUSAL[502] });
      return void res.json({ authRequired: true, authed: false });
    }
    res.json({ authRequired: true, authed: true, role: read.now.role, username: claims.username });
  });

  router.post("/auth/login", async (req, res) => {
    const { username, password } = req.body ?? {};
    if (typeof username !== "string" || typeof password !== "string") {
      return res.status(400).json({ error: "username and password required" });
    }
    const result = await login(daemon, username, password);
    if (!result.ok) return res.status(401).json({ error: result.error });
    issueCookiesFor(res, result.session);
    res.json({ ok: true });
  });

  router.post("/auth/logout", async (req, res) => {
    revokeLogin(req);
    await logout(daemon, refreshTokenOf(req));
    clearSessionCookies(res);
    res.json({ ok: true });
  });

  return router;
}
