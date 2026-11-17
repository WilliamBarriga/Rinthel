import path from "node:path";
import type { Workspace } from "@deck/contract";

export type { Workspace };

export type WorkspaceCreated =
  | { ok: true; workspace: Workspace }
  | { ok: false; status: 400 | 409 | 500; error: string };

export type WorkspaceResolved = { ok: true; path: string } | { ok: false; error: string };

/**
 * The directories a `task` Session may work in: everything directly under one root. The rules (a name
 * becomes a slug, nothing escapes the root, an existing one is not recreated) live here; an adapter
 * only says what is on disk. `FsWorkspaces` (workspaces-fs.ts) is the real one, `InMemoryWorkspaces`
 * the double.
 */
export interface Workspaces {
  readonly root: string;
  list(): Workspace[];
  /** "Cool Project" becomes the directory "cool-project". */
  create(rawName: string): WorkspaceCreated;
  /** The absolute path of a workspace a Session asks for, refused when outside the root or missing. */
  resolve(requested: string): WorkspaceResolved;
}

export function slugify(raw: string): string {
  return raw.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().trim()
    .replace(/[^a-z0-9._-]+/g, "-").replace(/-+/g, "-").replace(/^[-.]+|[-.]+$/g, "").slice(0, 64);
}

/** `requested` (a name, or an absolute path) inside `root`, or null when it would leave it. */
export function insideRootOrNull(root: string, requested: string): string | null {
  const base = path.resolve(root);
  const resolved = path.resolve(base, requested);
  return resolved === base || resolved.startsWith(base + path.sep) ? resolved : null;
}

/** The rules of `create`, before anything touches a disk: the folder name and where it goes, or why not. */
export function planWorkspace(root: string, rawName: string): { name: string; target: string } | { status: 400; error: string } {
  const name = slugify(rawName);
  if (!name) return { status: 400, error: `"${rawName}" no da un nombre de carpeta usable` };
  const target = insideRootOrNull(root, name);
  if (target === null || target === path.resolve(root)) return { status: 400, error: "Nombre de workspace inválido" };
  return { name, target };
}

export const OUTSIDE_WORKSPACE_ROOT = "el workspace tiene que estar dentro de la raíz de workspaces";

export class InMemoryWorkspaces implements Workspaces {
  readonly root: string;
  private readonly dirs = new Set<string>();

  constructor(root: string, existing: string[] = []) {
    this.root = path.resolve(root);
    for (const name of existing) this.dirs.add(name);
  }

  list(): Workspace[] {
    return [...this.dirs].sort().map((name) => ({ name, path: path.join(this.root, name), isGit: false }));
  }

  create(rawName: string): WorkspaceCreated {
    const plan = planWorkspace(this.root, rawName);
    if ("error" in plan) return { ok: false, ...plan };
    if (this.dirs.has(plan.name)) return { ok: false, status: 409, error: `El workspace "${plan.name}" ya existe` };
    this.dirs.add(plan.name);
    return { ok: true, workspace: { name: plan.name, path: plan.target, isGit: false } };
  }

  resolve(requested: string): WorkspaceResolved {
    const resolved = insideRootOrNull(this.root, requested);
    if (resolved === null) return { ok: false, error: OUTSIDE_WORKSPACE_ROOT };
    return [...this.dirs].some((n) => path.join(this.root, n) === resolved) ? { ok: true, path: resolved } : { ok: false, error: "el workspace no existe" };
  }
}
