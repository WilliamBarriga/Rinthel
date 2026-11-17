import { createHash, timingSafeEqual } from "node:crypto";
import type { NextFunction, Request, Response } from "express";
import { admitAsService, serviceIdentity } from "./identity.js";

/**
 * The daemon's service credential on `/api`: `X-Rinthel-Service-Secret` plus `X-Rinthel-User-Id`,
 * accepted on a closed list of routes and nowhere else. The list has one route: the daemon, about to
 * delete a user, retires their Sessions (`POST /agent/retire-sessions`). The service acts as the
 * user: a minimal member identity (id only, never admin).
 *
 * Rules, fixed:
 *  - A request that carries the secret header is judged by the credential alone: its cookies are
 *    dropped, so a cookie never raises the credential and a credential never rescues a cookie.
 *    Mounted before every other router, so the header closes every route off the list too.
 *  - Anything the credential does not clear (wrong or empty secret, no secret configured, a route
 *    off the list, a missing or malformed user id) is a 401, the same answer as to a caller with
 *    no credential.
 *  - The user is not checked against the daemon: the retire route is called for users that are
 *    already disabled, and only reaches the Sessions the id owns.
 *  - Nothing the caller sent is echoed or logged; a failed attempt logs its instant, method and route.
 */

/** Constant-time equality that never throws and never matches an empty or missing side. */
export function sameSecret(given: string | undefined, expected: string | undefined): boolean {
  if (!given || !expected) return false;
  // Hashing first gives both sides one length, so the comparison does not leak the secret's.
  const digest = (s: string) => createHash("sha256").update(s).digest();
  return timingSafeEqual(digest(given), digest(expected));
}

/** The closed list: exact method and exact path (no trailing slash, no case folding, no decoding). */
const ALLOWED: ReadonlyArray<{ method: string; path: RegExp }> = [
  { method: "POST", path: /^\/agent\/retire-sessions$/ },
];

const SECRET_HEADER = "x-rinthel-service-secret";
const USER_HEADER = "x-rinthel-user-id";

export function serviceCredential({ secret }: { secret: string | undefined }) {
  return (req: Request, res: Response, next: NextFunction): void => {
    if (req.headers[SECRET_HEADER] === undefined) return next();

    // The credential decides alone.
    req.cookies = {};
    delete req.headers.cookie;
    const refuse = () => {
      console.warn(`[deck] service credential refused: ${new Date().toISOString()} ${req.method} ${JSON.stringify(req.path)}`);
      res.status(401).json({ error: "Unauthorized" });
    };

    const header = (name: string) => {
      const v = req.headers[name];
      return typeof v === "string" ? v : undefined;
    };
    if (!sameSecret(header(SECRET_HEADER), secret)) return refuse();
    if (!ALLOWED.some((a) => a.method === req.method && a.path.test(req.path))) return refuse();
    const rawId = header(USER_HEADER);
    if (!rawId || !/^[1-9][0-9]{0,15}$/.test(rawId)) return refuse();

    admitAsService(req, serviceIdentity(Number(rawId)));
    next();
  };
}
