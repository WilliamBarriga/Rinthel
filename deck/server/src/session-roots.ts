import path from "node:path";
import { InMemoryWorkspaces, type Workspaces } from "./workspaces.js";

/**
 * Where Sessions live on Deck's volume: each Session's pi directory, each owner's Agent home (where an
 * `agent` Session works and its SOUL.md, PrimaryUser.md and MEMORY.md are read), and the workspaces a
 * `task` Session may open on: the Instance's for the general Agent (an admin), the owner's own for a
 * member, never a root that holds other users. `FsSessionRoots` (session-roots-fs.ts) is the real one.
 */
export interface SessionRoots {
  sessionDir(sessionId: string): string;
  agentHome(ownerUserId: number): string;
  workspaces(ownerUserId: number, general: boolean): Workspaces;
  /** Deletes a Session's pi directory for good; one that is not there is fine. */
  discard(sessionId: string): Promise<void>;
}

/** Session ids are Deck's own (`nanoid`): nothing else names a directory. */
export const SESSION_ID = /^[A-Za-z0-9_-]+$/;

/** Where a Session works: an `agent` Session in its owner's home; a `task` Session in the workspace it was created on, among those its profile reaches. */
export function workspaceOf(
  roots: SessionRoots,
  session: { kind: string; owner_user_id: number; workspace: string },
  general: boolean,
): string {
  if (session.kind === "agent") return roots.agentHome(session.owner_user_id);
  const found = roots.workspaces(session.owner_user_id, general).resolve(session.workspace);
  if (!found.ok) throw new Error(`El workspace de esta Sesión no está disponible para su dueño: ${found.error}`);
  return found.path;
}

/** The double: paths under `root`, workspaces in memory. */
export class InMemorySessionRoots implements SessionRoots {
  readonly discarded: string[] = [];
  private readonly spaces = new Map<string, InMemoryWorkspaces>();

  constructor(private readonly root = "/deck") {}

  sessionDir(sessionId: string): string {
    return path.join(this.root, "sessions", sessionId);
  }

  agentHome(ownerUserId: number): string {
    return path.join(this.root, "users", String(ownerUserId), "agent");
  }

  workspaces(ownerUserId: number, general: boolean): Workspaces {
    const key = general ? "instance" : String(ownerUserId);
    let found = this.spaces.get(key);
    if (!found) {
      found = new InMemoryWorkspaces(general ? path.join(this.root, "workspaces") : path.join(this.root, "users", key, "workspaces"));
      this.spaces.set(key, found);
    }
    return found;
  }

  async discard(sessionId: string): Promise<void> {
    this.discarded.push(sessionId);
  }
}
