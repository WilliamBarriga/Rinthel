import express, { type Router } from "express";
import { requireService } from "../identity.js";
import { discardSession, type DiscardDeps } from "../discard-session.js";

/** What retiring needs of the Sessions that run: stop one's pi before it is discarded. */
export interface SessionRuntime {
  stop(sessionId: string): Promise<void>;
}

/**
 * `POST /agent/retire-sessions`: the daemon, about to delete a user, retires every Session that user
 * owns (`task` and `agent`), stopping each one's pi first and dropping its files and slots. Service
 * credential only (a browser cookie, an admin's too, is 403) and only for the user the credential acts
 * as. Idempotent: whatever a failed call left is retired by the next one, and a user with nothing to
 * retire answers `{ retired: 0 }`. A failure is a 500, and the daemon keeps the user.
 */
export function userSessionsRouter(deps: DiscardDeps & { runtime: SessionRuntime }): Router {
  const { store, runtime } = deps;
  const router = express.Router();

  router.post("/agent/retire-sessions", async (req, res) => {
    const identity = requireService(req, res);
    if (!identity) return;
    try {
      const owned = await store.sessions.listOwnedBy(identity.userId);
      for (const session of owned) {
        await runtime.stop(session.id);
        await discardSession(session, deps);
      }
      res.json({ retired: owned.length });
    } catch (e) {
      res.status(500).json({ error: (e as Error).message });
    }
  });

  return router;
}
