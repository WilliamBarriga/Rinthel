import express, { type Request } from "express";
import type { CanvasActionResponse } from "@deck/contract";
import type { PortalStore } from "../store/port.js";
import type { Canvases } from "../canvases.js";
import { CanvasActionError, type CanvasActions } from "../canvas-actions.js";
import { sessionFor, sessionStreamAccess } from "../session-owner.js";

/** What the routes ask of the Canvases: the list, the stream's emitter and the three writes a person may start. */
export type CanvasesRuntime = Pick<Canvases, "events" | "persistCanvas" | "listCanvases" | "createCanvas" | "deleteCanvas">;

/**
 * The Canvases of a Session, behind the Session's own access rule (its owner, or an admin): the
 * list, its SSE stream, creating one, storing a temporary one, deleting one, and the one action of
 * a `ui` canvas that leaves the browser («ask the agent»: it answers 200 and starts no turn).
 * The content of a canvas is written by the Agent only; there is no route to write it.
 */
export function canvasesRouter({ store, canvases, actions, allowed }: {
  store: Pick<PortalStore, "sessions">;
  canvases: CanvasesRuntime;
  actions: CanvasActions;
  allowed?: (req: Request) => Promise<boolean>;
}) {
  const { events, persistCanvas, listCanvases, createCanvas, deleteCanvas } = canvases;
  const router = express.Router();
  router.use("/sessions/:id/canvases", async (req, res, next) => {
    if (await sessionFor(store, req, res)) next();
  });
  router.get("/sessions/:id/canvases", async (req, res) => res.json(await listCanvases(String(req.params.id))));
  router.get("/sessions/:id/canvases/events", async (req, res) => {
    const session = String(req.params.id);
    res.set({ "Content-Type": "text/event-stream", "Cache-Control": "no-cache", Connection: "keep-alive", "X-Accel-Buffering": "no" });
    res.flushHeaders();
    const access = sessionStreamAccess(store, req, res, session, allowed);
    const send = (data: unknown) => {
      const chunk = `data: ${JSON.stringify(data)}\n\n`;
      void access.send(() => { res.write(chunk); }, Buffer.byteLength(chunk));
    };
    events.on(session, send);
    send({ type: "snapshot", canvases: await listCanvases(session) });
    const timer = setInterval(() => void access.send(() => { res.write(": keepalive\n\n"); }), 15000);
    res.on("close", () => { clearInterval(timer); events.off(session, send); });
  });
  router.post("/sessions/:id/canvases", async (req, res) => {
    try {
      if (typeof req.body?.title !== "string") throw new Error("Title required");
      res.json(await createCanvas(String(req.params.id), req.body.title, req.body.kind));
    } catch (e) { res.status(400).json({ error: (e as Error).message }); }
  });
  router.post("/sessions/:id/canvases/:canvasId/persist", async (req, res) => {
    try { res.json(await persistCanvas(String(req.params.id), String(req.params.canvasId))); }
    catch (e) { res.status(400).json({ error: (e as Error).message }); }
  });
  router.delete("/sessions/:id/canvases/:canvasId", async (req, res) => {
    try {
      const revision = req.body?.revision;
      if (!Number.isInteger(revision)) throw new Error("Revision required");
      await deleteCanvas(String(req.params.id), String(req.params.canvasId), revision);
      res.json({ ok: true });
    } catch (e) { res.status(409).json({ error: (e as Error).message }); }
  });
  router.post("/sessions/:id/canvases/:canvasId/actions", async (req, res) => {
    try {
      await actions.perform(String(req.params.id), String(req.params.canvasId), { action: req.body?.action, params: req.body?.params });
      res.json({ ok: true } satisfies CanvasActionResponse);
    } catch (e) { res.status(e instanceof CanvasActionError ? e.status : 500).json({ error: (e as Error).message }); }
  });
  return router;
}
