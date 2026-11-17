import { mkdirSync } from "node:fs";
import { rm } from "node:fs/promises";
import path from "node:path";
import { SESSION_ID, type SessionRoots } from "./session-roots.js";
import { FsWorkspaces } from "./workspaces-fs.js";
import type { Workspaces } from "./workspaces.js";

/**
 * `SessionRoots` on Deck's volume (`DATA_DIR`, `/data` in the container):
 *
 *     sessions/<id>/             each Session's pi files
 *     users/<id>/agent/          an owner's Agent home
 *     users/<id>/workspaces/     a member's workspaces
 *     workspaces/                the Instance's workspaces (`WORKSPACE_ROOT`), the admin's
 */
export class FsSessionRoots implements SessionRoots {
  constructor(private readonly dataDir: string, private readonly instanceWorkspaces: string) {}

  sessionDir(sessionId: string): string {
    if (!SESSION_ID.test(sessionId)) throw new Error(`invalid Session id: ${sessionId}`);
    const dir = path.join(this.dataDir, "sessions", sessionId);
    mkdirSync(dir, { recursive: true });
    return dir;
  }

  agentHome(ownerUserId: number): string {
    const dir = path.join(this.dataDir, "users", String(Math.trunc(ownerUserId)), "agent");
    mkdirSync(dir, { recursive: true });
    return dir;
  }

  workspaces(ownerUserId: number, general: boolean): Workspaces {
    return new FsWorkspaces(general ? this.instanceWorkspaces : path.join(this.dataDir, "users", String(Math.trunc(ownerUserId)), "workspaces"));
  }

  async discard(sessionId: string): Promise<void> {
    if (!SESSION_ID.test(sessionId)) return;
    await rm(path.join(this.dataDir, "sessions", sessionId), { recursive: true, force: true });
  }
}
