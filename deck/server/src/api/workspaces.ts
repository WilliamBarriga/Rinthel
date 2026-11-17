import express, { type Router } from "express";
import type { SessionIdentity } from "../session-identity.js";
import type { SessionRoots } from "../session-roots.js";
import type { Workspaces } from "../workspaces.js";
import { requesterWorkspaces } from "./sessions.js";

/** The directories a `task` Session of the requester may open on: the Instance's for an admin, their own for a member. */
export function workspacesRouter(deps: { roots: SessionRoots; identity: SessionIdentity }): Router {
  const router = express.Router();
  const owned = async (req: express.Request, res: express.Response): Promise<Workspaces | null> => {
    try { return await requesterWorkspaces(req, deps); }
    catch { res.status(503).json({ error: "No se pudo verificar tu rol; inténtalo en un momento" }); return null; }
  };

  router.get("/workspaces", async (req, res) => {
    const found = await owned(req, res);
    if (found) res.json({ root: found.root, workspaces: found.list() });
  });

  router.post("/workspaces", async (req, res) => {
    const raw = req.body?.name;
    if (typeof raw !== "string" || !raw.trim()) return res.status(400).json({ error: "name required" });
    const found = await owned(req, res);
    if (!found) return;
    const created = found.create(raw);
    if (!created.ok) return res.status(created.status).json({ error: created.error });
    res.json(created.workspace);
  });

  return router;
}
