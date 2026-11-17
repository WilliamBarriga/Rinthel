import path from "node:path";
import express, { type Request, type Response, type Router } from "express";
import { nanoid } from "nanoid";
import type { Session } from "@deck/contract";
import { identityOf } from "../identity.js";
import { discardSession, type DiscardDeps } from "../discard-session.js";
import { canAccessSession, sessionFor, visibleSessions } from "../session-owner.js";
import type { SessionManager } from "../session-manager.js";
import type { SessionRoots } from "../session-roots.js";
import type { SessionIdentity } from "../session-identity.js";
import type { SessionRow } from "../store/port.js";
import { staffFraming } from "../staff-framing.js";
import { generalAgentFor, ToolProfileError, type ToolProfileRefusal } from "../tool-profile.js";
import type { Workspaces } from "../workspaces.js";

/** What the Session routes ask of the running Sessions (the `SessionManager`, or a double). */
export type SessionsRuntime = Pick<SessionManager, "isRunning" | "stop" | "prompt" | "respondUi" | "abort">;

/** The one place a row becomes a `Session`: the store keeps `pinned` as 0/1, the API speaks booleans. */
export const sessionToApi = (s: SessionRow, runtime: Pick<SessionsRuntime, "isRunning">): Session => ({
  id: s.id,
  title: s.title,
  workspace: s.workspace,
  executor: s.executor,
  status: s.status,
  created_at: s.created_at,
  updated_at: s.updated_at,
  last_error: s.last_error,
  pinned: Boolean(s.pinned),
  live: runtime.isRunning(s.id),
  provider: s.provider,
  model: s.model,
  thinking_level: s.thinking_level,
  kind: s.kind,
});

const PROFILE_REFUSAL_STATUS: Readonly<Record<ToolProfileRefusal, number>> = { owner_unverified: 502, owner_gone: 409 };

/**
 * How a failure to start or run a Session's Turn answers: an owner whose profile cannot be decided its
 * own code, anything else a 500 with the reason. One mapping for every route that starts pi.
 */
export function answerTurnFailure(res: Response, e: unknown, extra: Record<string, unknown> = {}): void {
  if (e instanceof ToolProfileError) res.status(PROFILE_REFUSAL_STATUS[e.reason]).json({ error: e.message, code: e.reason, ...extra });
  else res.status(500).json({ error: (e as Error).message, ...extra });
}

/**
 * The workspaces a `task` Session the requester opens would work in: the Instance's for the general
 * Agent (an admin, by the role the Instance has now), the requester's own for a member. Throws when
 * the identity does not answer.
 */
export async function requesterWorkspaces(req: Request, deps: { roots: SessionRoots; identity: SessionIdentity }): Promise<Workspaces> {
  const userId = identityOf(req)!.userId;
  const role = (await deps.identity.current(userId))?.role ?? null;
  return deps.roots.workspaces(userId, generalAgentFor(role));
}

const ROLE_UNVERIFIED = "No se pudo verificar tu rol; inténtalo en un momento";

/** Deck's Sessions: list, create, rename, discard, prompt, abort, and the browser's answer to a dialog. */
export function sessionsRouter(deps: DiscardDeps & {
  runtime: SessionsRuntime;
  roots: SessionRoots;
  identity: SessionIdentity;
}): Router {
  const { store, runtime, roots } = deps;
  const router = express.Router();
  const toApi = (s: SessionRow) => sessionToApi(s, runtime);
  const owner = (req: Request) => identityOf(req)!.userId;

  router.get("/sessions", async (req, res) => {
    res.json({ sessions: visibleSessions(req, await store.sessions.list()).map(toApi) });
  });

  router.get("/agent/sessions", async (req, res) => {
    res.json({ agentHome: roots.agentHome(owner(req)), sessions: visibleSessions(req, await store.sessions.listAgent()).map(toApi) });
  });

  /** A chat with the Agent, in the creator's Agent home. */
  router.post("/agent/sessions", async (req, res) => {
    const title = typeof req.body?.title === "string" && req.body.title.trim() ? req.body.title.trim().slice(0, 100) : "";
    const id = nanoid(12);
    await store.sessions.create({
      id,
      title: title || `Chat ${new Date().toISOString().slice(0, 16).replace("T", " ")}`,
      workspace: roots.agentHome(owner(req)),
      executor: "host",
      kind: "agent",
      owner_user_id: owner(req),
    });
    res.json(toApi((await store.sessions.get(id))!));
  });

  /** A `task` Session on one of the requester's workspaces. */
  router.post("/sessions", async (req, res) => {
    const { title, workspace } = req.body ?? {};
    if (typeof workspace !== "string" || !workspace) return res.status(400).json({ error: "workspace required" });
    let owned: Workspaces;
    try {
      owned = await requesterWorkspaces(req, deps);
    } catch {
      return res.status(503).json({ error: ROLE_UNVERIFIED });
    }
    const found = owned.resolve(workspace);
    if (!found.ok) return res.status(400).json({ error: found.error });
    const id = nanoid(12);
    await store.sessions.create({
      id,
      title: typeof title === "string" && title.trim() ? title.trim().slice(0, 100) : `${path.basename(found.path)} - ${nanoid(6)}`,
      workspace: found.path,
      executor: "host",
      kind: "task",
      owner_user_id: owner(req),
    });
    res.json(toApi((await store.sessions.get(id))!));
  });

  router.get("/sessions/:id", async (req, res) => {
    const session = await sessionFor(store, req, res);
    if (session) res.json(toApi(session));
  });

  router.patch("/sessions/:id", async (req, res) => {
    const session = await sessionFor(store, req, res);
    if (!session) return;
    const { title, pinned } = req.body ?? {};
    if (typeof title === "string" && title.trim()) await store.sessions.update(session.id, { title: title.trim().slice(0, 100) });
    if (typeof pinned === "boolean") await store.sessions.update(session.id, { pinned: pinned ? 1 : 0 });
    res.json(toApi((await store.sessions.get(session.id))!));
  });

  router.delete("/sessions/:id", async (req, res) => {
    const session = await sessionFor(store, req, res);
    if (!session) return;
    await runtime.stop(session.id);
    await discardSession(session, deps);
    res.json({ ok: true });
  });

  router.post("/sessions/:id/prompt", async (req, res) => {
    const session = await store.sessions.get(String(req.params.id));
    if (!session) return res.status(404).json({ error: "Sesión no encontrada" });
    if (!canAccessSession(req, session)) return res.status(403).json({ error: "Forbidden" });
    const message = req.body?.message;
    if (typeof message !== "string" || !message.trim()) return res.status(400).json({ error: "message required" });
    // Declared once, at the first prompt of any Session with an owner, never again.
    const framing = session.staff_framing_sent === 0 ? staffFraming(session.owner_user_id, identityOf(req)!) : undefined;
    try {
      // Returns as soon as pi takes the prompt; the run goes on whatever this browser does next.
      const { queued, turnId } = await runtime.prompt(session.id, message, framing ? { framing } : {});
      if (framing) await store.sessions.markStaffFramingSent(session.id);
      res.json({ ok: true, status: "running", queued, turn_id: turnId });
    } catch (e) {
      answerTurnFailure(res, e);
    }
  });

  router.post("/sessions/:id/ui-response", async (req, res) => {
    const session = await sessionFor(store, req, res);
    if (!session) return;
    const { id, value, cancelled } = req.body ?? {};
    if (typeof id !== "string") return res.status(400).json({ error: "id required" });
    const delivered = runtime.respondUi(session.id, id, { value, cancelled: Boolean(cancelled) });
    res.json({ ok: delivered });
  });

  router.post("/sessions/:id/abort", async (req, res) => {
    const session = await sessionFor(store, req, res);
    if (!session) return;
    await runtime.abort(session.id);
    res.json({ ok: true });
  });

  return router;
}
