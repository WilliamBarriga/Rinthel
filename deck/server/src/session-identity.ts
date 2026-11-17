import type { Role } from "@deck/contract";

/** Identity as read now from the Instance, independent of a token's stale role. */
export interface SessionPrincipal {
  userId: number;
  role: Role;
}

/**
 * `current` is the user's id and role as the Instance has them now, or `null` when the user is disabled or gone.
 * An answer that cannot be trusted (another user's id, an unknown role) or no answer at all throws: it never
 * yields a principal.
 */
export interface SessionIdentity {
  current(userId: number): Promise<SessionPrincipal | null>;
}

/** What a route that judges the caller by the current identity answers: through (`200`) or one of its refusals. */
export type IdentityAccess = 200 | 401 | 403 | 502;

/** The text of each refusal that is not the route's own `403`, the same over JSON (`{ error }`) and over a raw proxy. */
export const IDENTITY_REFUSAL = { 401: "Unauthorized", 502: "La identidad no está disponible" } as const;

/**
 * The one mapping from the current identity to an answer, shared by `adminOnly` and, through `readIdentity`,
 * `/auth/status`. `active` reads the identity now: `false` for a disabled or deleted user is a `401`, a throw (it
 * cannot be read) a `502`. Then `admin`, when the route asks for one, is a `403` if it says no.
 */
export async function identityAccess(active: () => Promise<boolean>, admin: () => boolean = () => true): Promise<IdentityAccess> {
  try {
    if (!await active()) return 401;
  } catch { return 502; }
  return admin() ? 200 : 403;
}

/**
 * `identityAccess` for a caller `sessionIdentityRouter` never saw (`/auth/status`), which reads the identity itself:
 * `read` is what the Instance says now, `null` for a disabled or deleted user. Its answer comes back with the `200`;
 * the refusals are the same `401` and `502`.
 */
export async function readIdentity<T>(read: () => Promise<T | null>): Promise<{ access: 200; now: T } | { access: 401 | 502 }> {
  let now: T | null = null;
  const access = await identityAccess(async () => (now = await read()) !== null);
  return access === 200 ? { access, now: now as T } : { access: access as 401 | 502 };
}

/**
 * The scriptable double: users with a role, `disable`/`remove` (both read as `null`, as from the daemon), `setRole`,
 * and `down` (no answer to trust at all).
 */
export class InMemorySessionIdentity implements SessionIdentity {
  private readonly users = new Map<number, Role | "disabled">();
  private failing = false;

  add(userId: number, role: Role = "miembro"): this { this.users.set(userId, role); return this; }
  setRole(userId: number, role: Role): this { return this.add(userId, role); }
  disable(userId: number): this { this.users.set(userId, "disabled"); return this; }
  remove(userId: number): this { this.users.delete(userId); return this; }
  /** The daemon does not answer. */
  down(): this { this.failing = true; return this; }
  /** The daemon answers again. */
  up(): this { this.failing = false; return this; }

  async current(userId: number): Promise<SessionPrincipal | null> {
    if (this.failing) throw new Error("La identidad no está disponible");
    const role = this.users.get(userId);
    return role === undefined || role === "disabled" ? null : { userId, role };
  }
}
