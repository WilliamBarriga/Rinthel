import type { SessionIdentity } from "./session-identity.js";
import { CANVAS_TOOLS } from "./pi/canvas-tools.js";

/**
 * `ToolProfile`: what a Session's Agent may call, decided by the current role of the Session's owner,
 * never by who is looking (an admin supervising a member's Session gets the member's profile).
 *
 * - Admin: the general Agent on the host: pi's built-ins, the extensions, skills and MCP of Deck's
 *   `agentDir`.
 * - Miembro: a closed list (`MEMBER_TOOLS`). Nothing of pi is loaded from disk, no built-in tool runs,
 *   and the Guard refuses anything outside the list.
 *
 * The role is read now through `SessionIdentity`; an owner that is gone, or an identity that does not
 * answer, is a `ToolProfileError` and the Session does not start. Nothing falls back to the general
 * Agent.
 */

/** What a member's Agent may call: it chats and writes Canvases (documents and interfaces), nothing else. */
export const MEMBER_TOOLS: readonly string[] = CANVAS_TOOLS;

export type ToolProfile =
  | { readonly kind: "general" }
  | { readonly kind: "miembro"; readonly tools: readonly string[] };

/** Why a profile could not be decided. */
export type ToolProfileRefusal = "owner_unverified" | "owner_gone";

export class ToolProfileError extends Error {
  override readonly name = "ToolProfileError";
  constructor(readonly reason: ToolProfileRefusal, message: string) {
    super(message);
  }
}

export function isClosed(profile: ToolProfile): profile is Extract<ToolProfile, { kind: "miembro" }> {
  return profile.kind !== "general";
}

/** Two profiles that would build the same Session: a live Session whose profile moved is relaunched. */
export function sameProfile(a: ToolProfile, b: ToolProfile): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

/** Whether a user whose role now is `role` gets the general Agent (and the Instance's workspaces). */
export function generalAgentFor(role: "admin" | "miembro" | null): boolean {
  return role === "admin";
}

export async function toolProfileFor(ownerUserId: number, identity: SessionIdentity): Promise<ToolProfile> {
  let owner;
  try {
    owner = await identity.current(ownerUserId);
  } catch {
    throw new ToolProfileError("owner_unverified", "No se pudo verificar al dueño de la Sesión; la Sesión no se inicia");
  }
  if (!owner || owner.userId !== ownerUserId) {
    throw new ToolProfileError("owner_gone", "El dueño de la Sesión ya no existe o está deshabilitado; la Sesión no se inicia");
  }
  return generalAgentFor(owner.role) ? { kind: "general" } : { kind: "miembro", tools: MEMBER_TOOLS };
}
