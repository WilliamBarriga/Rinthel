import express, { type Router, type Request } from "express";
import { eventTime } from "../event-time.js";
import { sessionFor, sessionStreamAccess } from "../session-owner.js";
import type { SessionManager } from "../session-manager.js";
import type { PortalStore } from "../store/port.js";

/** What the event stream asks of the running Sessions: live events and the snapshot of what is in flight. */
export type SessionEventsRuntime = Pick<SessionManager, "on" | "off" | "liveSnapshot">;

/**
 * How much of a long conversation a fresh page load replays.
 *
 * Small on purpose. Not a correctness limit — a reconnect with a cursor still
 * receives everything it missed, and older events are fetched on demand as you
 * scroll back. Replaying twenty thousand meant a refresh rendered the entire
 * history and then visibly scrolled through it.
 */
export const REPLAY_EVENTS = 1_200;

interface EventRow {
  seq: number;
  type: string;
  payload: string;
  created_at?: string;
}

/**
 * Replay-then-tail. The client passes the last seq it saw, so reconnecting
 * after minutes or days delivers exactly what was missed and then continues
 * live — no gap, no duplicates.
 */
export function sessionEventsRouter({ store, runtime, allowed, replayEvents = REPLAY_EVENTS }: {
  store: PortalStore;
  runtime: SessionEventsRuntime;
  replayEvents?: number;
  allowed?: (req: Request) => Promise<boolean>;
}): Router {
  const router = express.Router();

  /** What came before a cursor: the transcript scrolling back rather than forward. */
  router.get("/sessions/:id/events/before", async (req, res) => {
    const session = await sessionFor(store, req, res);
    if (!session) return;
    const before = Number(req.query.before ?? 0) || 0;
    const limit = Math.min(Number(req.query.limit) || 1200, 3000);
    const rows = await store.sessions.eventsBefore(session.id, before, limit);
    res.json({
      events: rows.map((r) => ({
        seq: r.seq,
        type: r.type,
        at: eventTime(r.created_at),
        payload: JSON.parse(r.payload),
      })),
      // Whether asking again would return anything, so the UI knows to stop.
      more: rows.length === limit,
    });
  });

  router.get("/sessions/:id/events", async (req, res) => {
    const session = await sessionFor(store, req, res);
    if (!session) return;

    if (allowed && !await allowed(req)) return res.status(401).json({ error: "Unauthorized" });
    const access = sessionStreamAccess(store, req, res, session.id, allowed);
    const since = Number(req.query.since ?? 0) || 0;

    res.writeHead(200, {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    });

    const write = (row: EventRow) => access.send(() => {
      res.write(`${row.seq > 0 ? `id: ${row.seq}\n` : ""}data: ${JSON.stringify({
        seq: row.seq,
        type: row.type,
        // What the activity line counts from, so a refresh mid-run still knows
        // how long the agent has been on this rather than starting from zero.
        at: eventTime(row.created_at),
        payload: JSON.parse(row.payload),
      })}\n\n`);
    }, Buffer.byteLength(row.payload) + 256);

    // Subscribed before the replay reads anything: the store is async, and an
    // event published while it answers would otherwise fall between the replay
    // and the subscription. Held back until the replay has been sent.
    let lastSent = 0;
    let replaying = true;
    const held: EventRow[] = [];
    let heldBytes = 0;
    const onEvent = (row: EventRow) => {
      if (!access.isOpen()) return;
      if (replaying) {
        heldBytes += Buffer.byteLength(row.payload) + 256;
        if (held.length >= 128 || heldBytes > 8_000_000) { held.length = 0; access.close(); return; }
        held.push(row);
        return;
      }
      // Live-only events carry a negative seq: deliver them, but never let one
      // move the replay cursor, or a reconnect would skip stored history.
      if (row.seq < 0) {
        write(row);
        return;
      }
      // Guard against double-sending anything the replay already covered.
      if (row.seq <= lastSent) return;
      lastSent = row.seq;
      write(row);
    };
    runtime.on(`session:${session.id}`, onEvent);

    const heartbeat = setInterval(() => void access.send(() => { res.write(": ping\n\n"); }), 25_000);
    res.on("close", () => {
      held.length = 0;
      clearInterval(heartbeat);
      runtime.off(`session:${session.id}`, onEvent);
    });

    // Replace stale in-memory deltas before durable replay, then restore the current snapshot.
    await access.send(() => { res.write("event: live-reset\ndata: {}\n\n"); });

    // A fresh load gets the end of the conversation, not the beginning. Replaying
    // from zero and stopping at the batch limit is how a long session came back
    // from a refresh showing its first few thousand events and nothing since —
    // the transcript ended mid-turn, on whatever the cap happened to land on.
    const cursor = since === 0 ? await store.sessions.replayStart(session.id, replayEvents) : since;

    // Paged to the end rather than one batch: a reconnect after a long run has
    // more to catch up on than a single query returns, and stopping early loses
    // exactly the part it was reconnecting for.
    lastSent = cursor;
    for (;;) {
      if (!access.isOpen()) return;
      const batch = await store.sessions.eventsSince(session.id, lastSent);
      if (!batch.length) break;
      for (const row of batch) {
        if (!access.isOpen()) return;
        await write(row);
        lastSent = row.seq;
      }
      if (batch.length < 5000) break;
    }
    for (const row of runtime.liveSnapshot(session.id)) await write(row);
    await access.send(() => { res.write(`event: caught-up\ndata: ${JSON.stringify({ seq: lastSent })}\n\n`); });

    replaying = false;
    for (const row of held) onEvent(row);
  });

  return router;
}
