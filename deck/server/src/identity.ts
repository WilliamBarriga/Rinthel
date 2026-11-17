import type { IncomingMessage } from "node:http";
import type { NextFunction, Request, Response } from "express";
import jwt from "jsonwebtoken";
import { createHash } from "node:crypto";
import type { LoginSession, Role } from "@deck/contract";
import type { DaemonClient } from "./daemon-client.js";

/**
 * Panel token: each person logs into the panel as themselves. The daemon signs the access token at
 * login; Deck validates it here with the shared secret, without a round trip to the daemon on every
 * request. Only the refresh (when the access token expires) reaches the daemon, transparently for
 * the front: see `requireAuth` below.
 *
 * There is no open mode: without `RINTHEL_PANEL_SECRET` no token validates, every route behind the
 * login answers 401, and `index.ts` refuses to start.
 */

export const PANEL_SECRET = process.env.RINTHEL_PANEL_SECRET || "";

export const ACCESS_COOKIE = "pi_panel_access";
const REFRESH_COOKIE = "pi_panel_refresh";
// The refresh cookie lasts at most what a freshly issued refresh token would
// (RINTHEL_IDENTITY_REFRESH_TTL, 30 days by default). If the daemon is set
// shorter, its own /identity/refresh refuses it before the cookie expires;
// this only avoids sending a cookie already known to be useless.
const REFRESH_COOKIE_MAX_AGE_MS = 30 * 24 * 60 * 60 * 1000;

export interface PanelClaims {
  userId: number;
  username: string;
  role: Role;
}

function claimsOf(session: LoginSession): PanelClaims {
  return { userId: session.user.id, username: session.user.username, role: session.user.role };
}

/**
 * Logins logged out in this process, and the streams open under each login. Process state of this
 * adapter (the cookie/JWT auth), not a port: an Instance runs one Deck process, nothing else reads
 * or writes this, and an in-memory adapter behind an interface would be this same Map. It keeps
 * token hashes only, each until its access token expires. A restart forgets it: every stream is
 * closed by then, and an access token logged out before the restart is accepted again only until
 * its own short expiry.
 */
const revokedAccess = new Map<string, number>();
const logoutWatchers = new Map<string, Set<() => void>>();
const tokenKey = (token: string) => createHash("sha256").update(token).digest("hex");

/** Close active streams of this login, and reject its access token until it expires. */
export function revokeLogin(req: Request): void {
  const token = req.cookies?.[ACCESS_COOKIE];
  if (typeof token === "string" && verifyAccessToken(token)) {
    const payload = jwt.decode(token);
    if (payload && typeof payload === "object" && typeof payload.exp === "number") revokedAccess.set(tokenKey(token), payload.exp * 1000);
  }
  for (const key of loginKeys(req)) for (const close of [...(logoutWatchers.get(key) ?? [])]) close();
}

function loginKeys(req: Request): string[] {
  return [...new Set([req.cookies?.[ACCESS_COOKIE], req.cookies?.[REFRESH_COOKIE], accessTokenOf(req)]
    .filter((v): v is string => typeof v === "string" && v.length > 0).map(tokenKey))];
}

/** Registered only while a stream is open; no tokens are stored in the registry. */
export function watchLogin(req: Request, close: () => void): () => void {
  const keys = loginKeys(req);
  for (const key of keys) {
    const watchers = logoutWatchers.get(key) ?? new Set();
    watchers.add(close);
    logoutWatchers.set(key, watchers);
  }
  return () => {
    for (const key of keys) {
      const watchers = logoutWatchers.get(key);
      watchers?.delete(close);
      if (!watchers?.size) logoutWatchers.delete(key);
    }
  };
}

export function accessStillValid(req: Request): boolean {
  return isServiceRequest(req) || verifyAccessToken(accessTokenOf(req) ?? req.cookies?.[ACCESS_COOKIE]) !== null;
}

function verifyAccessToken(token: string | undefined): PanelClaims | null {
  if (!token || !PANEL_SECRET) return null;
  for (const [key, expires] of revokedAccess) if (expires <= Date.now()) revokedAccess.delete(key);
  if (revokedAccess.has(tokenKey(token))) return null;
  try {
    const claims = jwt.verify(token, PANEL_SECRET, { algorithms: ["HS256"] }) as jwt.JwtPayload;
    if (claims.typ !== "access") return null;
    return { userId: Number(claims.sub), username: claims.username, role: claims.role };
  } catch {
    return null;
  }
}

/** The daemon's `/identity/*` login routes take no credential; the call goes as the service. */
async function daemonPost(daemon: DaemonClient, path: string, body: unknown): Promise<{ ok: boolean; json: any }> {
  try {
    const resp = await daemon.asService().fetch(path, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    const json = await resp.json().catch(() => ({}));
    return { ok: resp.ok, json };
  } catch (err) {
    return { ok: false, json: { error: (err as Error).message } };
  }
}

function setSessionCookies(res: Response, session: LoginSession): void {
  const secure = Boolean(process.env.PORTAL_TLS_CERT);
  res.cookie(ACCESS_COOKIE, session.access_token, {
    httpOnly: true,
    sameSite: "lax",
    secure,
    maxAge: session.access_expires_in * 1000,
  });
  res.cookie(REFRESH_COOKIE, session.refresh_token, {
    httpOnly: true,
    sameSite: "lax",
    secure,
    maxAge: REFRESH_COOKIE_MAX_AGE_MS,
  });
}

export function clearSessionCookies(res: Response): void {
  res.clearCookie(ACCESS_COOKIE);
  res.clearCookie(REFRESH_COOKIE);
}

export async function login(
  daemon: DaemonClient,
  username: string,
  password: string
): Promise<{ ok: true; session: LoginSession } | { ok: false; error: string }> {
  const { ok, json } = await daemonPost(daemon, "/identity/login", { username, password });
  if (!ok) return { ok: false, error: typeof json.detail === "string" ? json.detail : "invalid credentials" };
  return { ok: true, session: json as LoginSession };
}

export function issueCookiesFor(res: Response, session: LoginSession): void {
  setSessionCookies(res, session);
}

export function refreshTokenOf(req: Request): string | undefined {
  return req.cookies?.[REFRESH_COOKIE];
}

export async function logout(daemon: DaemonClient, refreshToken: string | undefined): Promise<void> {
  if (!refreshToken) return;
  await daemonPost(daemon, "/identity/logout", { refresh_token: refreshToken });
}

type AuthedRequest = Request & { identity?: PanelClaims; accessToken?: string };

const serviceRequests = new WeakSet<Request>();

/**
 * The service credential middleware (`service-credential.ts`) vouched for this request: `claims`
 * become its identity and `requireAuth` lets it through without a cookie. Only that module calls it.
 */
export function admitAsService(req: Request, claims: PanelClaims): void {
  Object.assign(req as AuthedRequest, { identity: claims });
  serviceRequests.add(req);
}

/** The identity the service credential acts as: the user's id only, a member, never admin. */
export function serviceIdentity(userId: number): PanelClaims {
  return { userId, username: "", role: "miembro" };
}

/**
 * The guard of a route only the service may call: the identity the credential acts as, or `null`
 * once a 403 has been sent (a browser cookie, an admin's too, is refused).
 */
export function requireService(req: Request, res: Response): PanelClaims | null {
  const identity = identityOf(req);
  if (!isServiceRequest(req) || !identity) {
    res.status(403).json({ error: "Forbidden" });
    return null;
  }
  return identity;
}

/** Whether the service credential admitted this request (a route only the service may call checks it). */
export function isServiceRequest(req: Request): boolean {
  return serviceRequests.has(req);
}

/**
 * Validates the access token locally. If it expired but there is a refresh token in its cookie, it
 * calls the daemon once (`/identity/refresh`, single-use rotation), re-issues both cookies and goes
 * on with the original request: the front never learns there was a refresh.
 */
export const requireAuth =
  (daemon: DaemonClient) =>
  async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    if (serviceRequests.has(req)) return next();

    const rawToken = req.cookies?.[ACCESS_COOKIE];
    const direct = verifyAccessToken(rawToken);
    if (direct) {
      Object.assign(req as AuthedRequest, { identity: direct, accessToken: rawToken });
      return next();
    }

    const refreshToken = refreshTokenOf(req);
    if (refreshToken && PANEL_SECRET) {
      const { ok, json } = await daemonPost(daemon, "/identity/refresh", { refresh_token: refreshToken });
      if (ok) {
        const session = json as LoginSession;
        setSessionCookies(res, session);
        // The token just re-issued, not the stale cookie the browser sent, so a caller forwarding
        // it to the daemon (`daemon-proxy.ts`) sends one the daemon still recognises.
        Object.assign(req as AuthedRequest, { identity: claimsOf(session), accessToken: session.access_token });
        return next();
      }
    }

    clearSessionCookies(res);
    res.status(401).json({ error: "Unauthorized" });
  };

/** Whether the request's access cookie is valid now. */
export function isAuthed(req: Request): boolean {
  return verifyAccessToken(req.cookies?.[ACCESS_COOKIE]) !== null;
}

/** Whether an identity may use the admin routes. No identity, no admin: there is no open mode. */
export function isAdminIdentity(identity: PanelClaims | null): boolean {
  return identity?.role === "admin";
}

/** The verified claims of a raw request (a websocket upgrade, or a proxy mounted outside `/api`); null with no valid cookie. */
export function claimsOfRequest(req: IncomingMessage): PanelClaims | null {
  const header = req.headers.cookie ?? "";
  const pair = header.split(";").map((c) => c.trim()).find((c) => c.startsWith(`${ACCESS_COOKIE}=`));
  const token = pair ? decodeURIComponent(pair.slice(ACCESS_COOKIE.length + 1)) : undefined;
  return verifyAccessToken(token);
}

/** Set by `requireAuth` once the request has passed. */
export function identityOf(req: Request): PanelClaims | null {
  return (req as AuthedRequest).identity ?? null;
}

/**
 * The raw access token `requireAuth` validated this request with, already refreshed if it needed
 * to be: what a caller forwards as a Bearer token to the daemon, not the request's own cookie,
 * which can be the stale one `requireAuth` just replaced.
 */
export function accessTokenOf(req: Request): string | null {
  return (req as AuthedRequest).accessToken ?? null;
}
