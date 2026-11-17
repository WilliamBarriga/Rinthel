import express, { type Request, type Router } from "express";
import { accessStillValid, identityOf, isAdminIdentity, isServiceRequest } from "../identity.js";
import { IDENTITY_REFUSAL, identityAccess, type SessionIdentity } from "../session-identity.js";

/** Re-read disabled/deleted users and stale admin roles. Service callers remain members. */
export async function refreshSessionIdentity(req: Request, identity: SessionIdentity): Promise<boolean> {
  const claims = identityOf(req);
  if (!claims) return false;
  const current = await identity.current(claims.userId);
  if (!current) return false;
  claims.role = isServiceRequest(req) ? "miembro" : current.role;
  return true;
}

/** The refresh `sessionIdentityRouter` leaves on a cookie request, run at most once per request. */
const pendingRefresh = new WeakMap<Request, () => Promise<boolean>>();

/**
 * The caller's identity as the Instance has it now, for a route that judges the role: `true` once the request's role is
 * the current one, `false` for a disabled or deleted user; it throws when the identity cannot be read. A request
 * `sessionIdentityRouter` never saw (a service call, a router mounted alone in a test) keeps the role it came with.
 */
export function currentIdentity(req: Request): Promise<boolean> {
  return pendingRefresh.get(req)?.() ?? Promise.resolve(true);
}

/**
 * Whether the caller is an admin now, for a long stream that re-checks while it stays open: the access token is still
 * valid (not expired, not logged out) and the role is read again on every call; an identity that cannot be read is not
 * an admin.
 */
export function stillAdmin(identity: SessionIdentity): (req: Request) => Promise<boolean> {
  return async (req) => {
    try { return accessStillValid(req) && await refreshSessionIdentity(req, identity) && isAdminIdentity(identityOf(req)); }
    catch { return false; }
  };
}

/**
 * Mounted after authentication and before every route that judges the caller. On every cookie request it leaves the
 * refresh for `currentIdentity`, which `adminOnly` awaits: an admin route reads the role the Instance has now instead
 * of the one in the access token, so a demoted admin loses it on the next request instead of when the token expires.
 *
 * It judges cookie callers only. A request the service credential admitted is never refreshed here: the retire route
 * is called by the daemon exactly for users that are disabled, so a refresh would answer 401 and the user could not
 * be deleted.
 *
 * The Session routes (`/sessions`, `/agent`, `/workspaces`) refresh here, before any of their handlers runs, since they
 * judge the caller in many places and not only through `adminOnly`. Actions fail closed when the identity cannot be
 * read; only a read of stored history goes on, with the reader as a member (`storedReadFallback`).
 */
export function sessionIdentityRouter(identity: SessionIdentity): Router {
  const router = express.Router();
  router.use((req, _res, next) => {
    if (!isServiceRequest(req)) {
      let once: Promise<boolean> | null = null;
      pendingRefresh.set(req, () => (once ??= refreshSessionIdentity(req, identity)));
    }
    next();
  });
  router.use(["/sessions", "/agent", "/workspaces"], async (req, res, next) => {
    if (isServiceRequest(req)) return next();
    const access = await identityAccess(() => currentIdentity(req));
    if (access === 200) return next();
    if (access === 502 && storedReadFallback(req)) return next();
    res.status(access).json({ error: IDENTITY_REFUSAL[access as 401 | 502] });
  });
  return router;
}

/**
 * Whether a request reads stored history only: the Session lists, one Session, and its event log. Any other GET
 * (config, commands) can start a runtime, and is an action.
 */
export function readsStoredHistory(req: Pick<Request, "method" | "originalUrl">): boolean {
  const path = req.originalUrl.split("?")[0]!.replace(/^\/api(?=\/)/, "");
  return req.method === "GET" && (path === "/agent/sessions" || /^\/sessions(?:\/[^/]+(?:\/events(?:\/before)?)?)?$/.test(path));
}

/**
 * With the daemon down, a valid login still reads its own stored history, judged as a member: an admin sees only their
 * own Sessions until the identity answers again.
 */
function storedReadFallback(req: Request): boolean {
  const claims = identityOf(req);
  if (!claims || !accessStillValid(req) || !readsStoredHistory(req)) return false;
  claims.role = "miembro";
  return true;
}

/** For a long stream: the login still valid and the identity still current; a daemon down falls back like a stored read. */
export async function refreshSessionReader(req: Request, identity: SessionIdentity): Promise<boolean> {
  try { return accessStillValid(req) && await refreshSessionIdentity(req, identity); }
  catch { return storedReadFallback(req); }
}
