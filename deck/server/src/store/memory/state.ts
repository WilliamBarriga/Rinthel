import type { CanvasRecord, EventRow, SessionRow } from "../port.js";

export interface NoteRow {
  id: number;
  session_id: string;
  text: string;
  consumed: boolean;
  pending_delivery: boolean;
}

/**
 * What the repos of one memory store share. Sessions are the parent of events,
 * notes, canvases and the taint mark, as in the SQLite schema: a child needs its session to
 * exist, and goes with it.
 */
export interface MemoryState {
  sessions: Map<string, SessionRow>;
  events: EventRow[];
  notes: NoteRow[];
  canvases: Map<string, CanvasRecord>;
  /** The Sessions marked tainted. */
  tainted: Set<string>;
  /** The identity column of events and notes, shared across sessions and never reused. */
  nextSeq(table: "events" | "notes"): number;
}

export function newState(): MemoryState {
  const seqs = { events: 0, notes: 0 };
  return {
    sessions: new Map(),
    events: [],
    notes: [],
    canvases: new Map(),
    tainted: new Set(),
    nextSeq: (table) => ++seqs[table],
  };
}

/** The portal's timestamp text, `YYYY-MM-DD HH:MM:SS` in UTC. */
export function utcNow(): string {
  return new Date().toISOString().slice(0, 19).replace("T", " ");
}

/** A violated constraint (a duplicate key, a missing parent), as the SQLite adapter would throw. */
export class ConstraintViolation extends Error {}

export function mustExist(state: MemoryState, sessionId: string): void {
  if (!state.sessions.has(sessionId)) throw new ConstraintViolation(`session ${sessionId} does not exist`);
}
