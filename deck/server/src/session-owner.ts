import type { Request, Response } from "express";
import type { PortalStore, SessionRow } from "./store/port.js";
import { accessStillValid, identityOf, watchLogin } from "./identity.js";

/**
 * Who reaches a Session: its owner, and an admin (who supervises; the Session still acts for its
 * owner). A Session with no owner is nobody's, so only an admin reaches it.
 */
export function canAccessSession(req: Request, session: { owner_user_id: number | null }): boolean {
  const identity = identityOf(req);
  if (!identity) return false;
  return identity.role === "admin" || identity.userId === session.owner_user_id;
}

/** The rows the caller may see: the one owner rule every list applies. */
export function visibleSessions<T extends { owner_user_id: number | null }>(req: Request, sessions: T[]): T[] {
  return sessions.filter((s) => canAccessSession(req, s));
}

/** The Session in `:id` for a route acting on it, or `null` once a 404 or 403 has been sent. */
export async function sessionFor(store: Pick<PortalStore, "sessions">, req: Request, res: Response): Promise<SessionRow | null> {
  const session = await store.sessions.get(String(req.params.id));
  if (!session) {
    res.status(404).json({ error: "Sesión no encontrada" });
    return null;
  }
  if (!canAccessSession(req, session)) {
    res.status(403).json({ error: "Forbidden" });
    return null;
  }
  return session;
}

/**
 * A long stream's writes, in bounded batches that re-check before each batch that the login is still
 * valid, the identity still current (`allowed`) and the Session still the reader's. A slow reader is
 * closed and reconnects from its cursor instead of holding an unbounded queue.
 */
export function sessionStreamAccess(
  store: Pick<PortalStore, "sessions">, req: Request, res: Response, id: string,
  allowed: (req: Request) => Promise<boolean> = async () => true,
): { send(write: () => void | Promise<void>, bytes?: number): Promise<void>; close(): void; isOpen(): boolean } {
  type Write = { run: () => void | Promise<void>; resolve: () => void };
  let closed = false;
  let flushing = false;
  let queuedBytes = 0;
  const pending: Write[] = [];
  let unwatch = () => {};
  const close = () => {
    if (closed) return;
    closed = true;
    unwatch();
    for (const write of pending.splice(0)) write.resolve();
    queuedBytes = 0;
    res.end();
  };
  const flush = async () => {
    if (flushing || closed) return;
    flushing = true;
    try {
      while (pending.length && !closed) {
        const batch = pending.splice(0);
        queuedBytes = 0;
        try {
          const session = await store.sessions.get(id);
          if (!accessStillValid(req) || !await allowed(req) || !session || !canAccessSession(req, session)) { close(); return; }
          for (const write of batch) {
            if (closed) break;
            await write.run();
            if (res.writableLength > 2_000_000) close();
          }
        } catch { close(); }
        finally { for (const write of batch) write.resolve(); }
      }
    } finally { flushing = false; }
  };
  unwatch = watchLogin(req, close);
  res.once("close", close);
  return {
    close,
    isOpen: () => !closed,
    send(run, bytes = 1024) {
      if (closed) return Promise.resolve();
      if (pending.length >= 128 || queuedBytes + bytes > 8_000_000) { close(); return Promise.resolve(); }
      queuedBytes += bytes;
      return new Promise<void>((resolve) => {
        pending.push({ run, resolve });
        queueMicrotask(() => { void flush(); });
      });
    },
  };
}
