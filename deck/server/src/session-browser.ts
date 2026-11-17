import type { SessionIdentity } from "./session-identity.js";
import { ownerIsAdminNow } from "./tool-profile.js";

/** What the Guard's browser gate reads on each call, plus where the Instance browser is listening. */
export interface SessionBrowserState {
  allowed: boolean;
  allowlist: string[];
  /** CDP endpoint of the Instance browser; present only when `allowed`. */
  cdpEndpoint?: string;
}

export interface SessionBrowserOptions {
  /** The Session's owner (Identity user id), or null for a Session that has none. */
  owner: number | null;
  /** Who the owner is now: the role is read at each call, never kept. */
  identity: SessionIdentity;
  /** The Session's own toggle (`sessions.browser`), read at each call. */
  on: () => Promise<boolean>;
  allowlist: () => Promise<string[]>;
  /** The Instance browser's fixed CDP endpoint. */
  cdpEndpoint: string;
}

const SHUT: SessionBrowserState = { allowed: false, allowlist: [] };

/**
 * The browser gate of one Session: the Instance browser, shared by every Session that may drive it,
 * with no lease. Open only when the Session has an owner, its toggle is on, and the owner is an admin
 * now. Any other answer, including an identity, a toggle or an allowlist that cannot be read, shuts
 * the gate: it never fails open.
 *
 * Asking is not activity: the Instance browser is started and stopped by hand and never shut down
 * for being idle, so its logins stay alive.
 */
export function sessionBrowserNow(opts: SessionBrowserOptions): () => Promise<SessionBrowserState> {
  return async () => {
    if (opts.owner === null) return { ...SHUT };
    try {
      if (!(await opts.on())) return { ...SHUT };
      if (!(await ownerIsAdminNow(opts.owner, opts.identity))) return { ...SHUT };
      return { allowed: true, allowlist: await opts.allowlist(), cdpEndpoint: opts.cdpEndpoint };
    } catch {
      return { ...SHUT };
    }
  };
}
