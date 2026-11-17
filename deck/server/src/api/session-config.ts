import express, { type Router } from "express";
import type { SessionManager } from "../session-manager.js";
import { sessionFor } from "../session-owner.js";
import type { PortalStore } from "../store/port.js";
import { answerTurnFailure } from "./sessions.js";

/** What the per-Session config routes ask of the running Sessions. */
export type SessionConfigRuntime = Pick<SessionManager, "isRunning" | "client" | "compact">;

/**
 * Per-Session config: the composer's pills (model, context used, thinking effort), compaction and the
 * commands pi offers. Every route but the stored read starts the Session's pi, so a failure answers as
 * a Turn start does (`answerTurnFailure`).
 */
export function sessionConfigRouter(deps: { store: PortalStore; runtime: SessionConfigRuntime }): Router {
  const { store, runtime } = deps;
  const router = express.Router();

  router.get("/sessions/:id/config", async (req, res) => {
    const session = await sessionFor(store, req, res);
    if (!session) return;
    // Deliberately does not start pi: the pills need what is on the row, and starting a runtime for them costs seconds.
    if (!runtime.isRunning(session.id)) {
      return res.json({
        live: false,
        state: { model: { id: "", name: "sin iniciar", provider: "rinthel" }, thinkingLevel: session.thinking_level || "medium" },
        stats: null,
        thinking: { levels: [] },
      });
    }
    try {
      const client = await runtime.client(session.id);
      const [state, levels, stats] = await Promise.all([client.getState(), client.getThinkingLevels(), client.getStats()]);
      res.json({ live: true, state, thinking: { levels }, stats });
    } catch (e) {
      answerTurnFailure(res, e);
    }
  });

  router.post("/sessions/:id/config", async (req, res) => {
    const session = await sessionFor(store, req, res);
    if (!session) return;
    const { thinkingLevel } = req.body ?? {};
    if (typeof thinkingLevel !== "string" || !thinkingLevel) return res.status(400).json({ error: "thinkingLevel required" });
    try {
      const client = await runtime.client(session.id);
      await client.setThinkingLevel(thinkingLevel);
      const state = await client.getState();
      // What pi resolved, not what was asked: it coerces a level the model does not take.
      await store.sessions.update(session.id, { thinking_level: state.thinkingLevel });
      res.json({ ok: true, state });
    } catch (e) {
      answerTurnFailure(res, e);
    }
  });

  router.post("/sessions/:id/compact", async (req, res) => {
    const session = await sessionFor(store, req, res);
    if (!session) return;
    try {
      await runtime.compact(session.id);
      res.json({ ok: true });
    } catch (e) {
      answerTurnFailure(res, e);
    }
  });

  router.get("/sessions/:id/commands", async (req, res) => {
    const session = await sessionFor(store, req, res);
    if (!session) return;
    try {
      res.json({ commands: await (await runtime.client(session.id)).getCommands() });
    } catch (e) {
      answerTurnFailure(res, e);
    }
  });

  return router;
}
