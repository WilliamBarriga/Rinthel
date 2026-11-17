import { existsSync, mkdirSync, readdirSync, realpathSync, statSync } from "node:fs";
import path from "node:path";
import { insideRootOrNull, OUTSIDE_WORKSPACE_ROOT, planWorkspace, type Workspace, type WorkspaceCreated, type WorkspaceResolved, type Workspaces } from "./workspaces.js";

/** `Workspaces` on disk: the directories directly under `root`, created on first use. */
export class FsWorkspaces implements Workspaces {
  readonly root: string;

  constructor(root: string) {
    mkdirSync(root, { recursive: true });
    this.root = realpathSync(root);
  }

  list(): Workspace[] {
    return readdirSync(this.root, { withFileTypes: true })
      .filter((e) => e.isDirectory() && !e.name.startsWith("."))
      .map((e) => e.name)
      .sort()
      .map((name) => ({ name, path: path.join(this.root, name), isGit: existsSync(path.join(this.root, name, ".git")) }));
  }

  create(rawName: string): WorkspaceCreated {
    const plan = planWorkspace(this.root, rawName);
    if ("error" in plan) return { ok: false, ...plan };
    if (existsSync(plan.target)) return { ok: false, status: 409, error: `El workspace "${plan.name}" ya existe` };
    try {
      mkdirSync(plan.target);
    } catch (e) {
      return { ok: false, status: 500, error: (e as Error).message };
    }
    return { ok: true, workspace: { name: plan.name, path: plan.target, isGit: false } };
  }

  resolve(requested: string): WorkspaceResolved {
    const resolved = insideRootOrNull(this.root, requested);
    if (resolved === null || resolved === this.root) return { ok: false, error: OUTSIDE_WORKSPACE_ROOT };
    try {
      // A link inside the root that points out of it is outside.
      const real = realpathSync(resolved);
      if (insideRootOrNull(this.root, real) === null || !statSync(real).isDirectory()) return { ok: false, error: OUTSIDE_WORKSPACE_ROOT };
      return { ok: true, path: real };
    } catch {
      return { ok: false, error: "el workspace no existe" };
    }
  }
}
