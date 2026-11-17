import type { EventRow, SessionPatch, SessionRow, SessionsRepo } from "../port.js";
import { ConstraintViolation, mustExist, utcNow, type MemoryState } from "./state.js";

const PATCHABLE = ["title", "status", "last_error", "provider", "model", "thinking_level", "pinned", "pi_session_file"];

export function memorySessions(state: MemoryState, now: () => Date = () => new Date()): SessionsRepo {
  const { sessions } = state;
  /** Insertion order is the tie-break of the "most recently touched" listings: the later one first. */
  const newestFirst = (rows: SessionRow[]) => rows.reverse().sort((a, b) => (a.updated_at < b.updated_at ? 1 : a.updated_at > b.updated_at ? -1 : 0));
  const where = (keep: (s: SessionRow) => boolean) => [...sessions.values()].filter(keep).map((s) => ({ ...s }));
  const change = async (id: string, fields: Partial<SessionRow>) => {
    const row = sessions.get(id);
    if (row) Object.assign(row, fields);
  };

  /** Marks the matching notes and hands back their text, oldest first. */
  const takeNotes = (sessionId: string, matches: (n: (typeof state.notes)[number]) => boolean, mark: (n: (typeof state.notes)[number]) => void) => {
    const taken = state.notes.filter((n) => n.session_id === sessionId && matches(n));
    taken.forEach(mark);
    return taken.map((n) => n.text);
  };

  return {
    async create(row) {
      if (sessions.has(row.id)) throw new ConstraintViolation(`session ${row.id} exists`);
      const now = utcNow();
      sessions.set(row.id, {
        id: row.id,
        title: row.title,
        workspace: row.workspace,
        executor: row.executor,
        status: "idle",
        created_at: now,
        updated_at: now,
        last_error: null,
        provider: null,
        model: null,
        thinking_level: null,
        pinned: 0,
        pi_session_file: null,
        kind: row.kind ?? "task",
        browser: 0,
        owner_user_id: row.owner_user_id ?? null,
        staff_framing_sent: 0,
      });
    },

    async get(id) {
      const row = sessions.get(id);
      return row && { ...row };
    },

    async list(ownerUserId) {
      return newestFirst(where((s) => s.kind === "task" && (ownerUserId === undefined || s.owner_user_id === ownerUserId))).sort(
        (a, b) => b.pinned - a.pinned
      );
    },

    async listAgent() {
      return newestFirst(where((s) => s.kind === "agent"));
    },

    async listOwnedBy(ownerUserId) {
      return where((s) => s.owner_user_id === ownerUserId);
    },

    async listBrowserEnabled() {
      return newestFirst(where((s) => s.browser === 1));
    },

    async update(id, patch: SessionPatch) {
      const fields = Object.fromEntries(Object.entries(patch).filter(([k]) => PATCHABLE.includes(k)));
      if (Object.keys(fields).length) await change(id, { ...fields, updated_at: utcNow() });
    },

    setBrowser: (id, on) => change(id, { browser: on ? 1 : 0 }),
    markStaffFramingSent: (id) => change(id, { staff_framing_sent: 1 }),

    async delete(id) {
      sessions.delete(id);
      state.events = state.events.filter((e) => e.session_id !== id);
      state.notes = state.notes.filter((n) => n.session_id !== id);
      for (const [key, canvas] of state.canvases) if (canvas.session_id === id) state.canvases.delete(key);
    },

    async markOrphanedInterrupted() {
      const running = [...sessions.values()].filter((s) => s.status === "running");
      for (const s of running) Object.assign(s, { status: "interrupted", updated_at: utcNow() });
      return running.length;
    },

    async appendEvent(sessionId, type, payload) {
      mustExist(state, sessionId);
      const event: EventRow = {
        seq: state.nextSeq("events"),
        session_id: sessionId,
        type,
        payload: JSON.stringify(payload),
        created_at: now().toISOString().slice(0, 19).replace("T", " "),
      };
      state.events.push(event);
      return { ...event };
    },

    async replayStart(sessionId, keep) {
      const own = state.events.filter((e) => e.session_id === sessionId);
      return own[own.length - 1 - keep]?.seq ?? 0;
    },
    async hasEvent(sessionId, type) {
      return state.events.some(e => e.session_id === sessionId && e.type === type);
    },

    async eventsBefore(sessionId, before, limit = 1500) {
      return state.events
        .filter((e) => e.session_id === sessionId && e.seq < before)
        .slice(-limit)
        .map((e) => ({ ...e }));
    },

    async eventsSince(sessionId, since = 0, limit = 5000) {
      return state.events
        .filter((e) => e.session_id === sessionId && e.seq > since)
        .slice(0, limit)
        .map((e) => ({ ...e }));
    },

    async pruneEvents(before) {
      const cutoff = before.toISOString().slice(0, 19).replace("T", " ");
      const kept = state.events.filter((e) => e.created_at >= cutoff);
      const pruned = state.events.length - kept.length;
      state.events = kept;
      return pruned;
    },

    async addNote(sessionId, text, pendingDelivery = false) {
      mustExist(state, sessionId);
      state.notes.push({ id: state.nextSeq("notes"), session_id: sessionId, text, consumed: false, pending_delivery: pendingDelivery });
    },

    async takeDeliveries(sessionId) {
      return takeNotes(sessionId, (n) => n.pending_delivery, (n) => (n.pending_delivery = false));
    },

    async takeNotes(sessionId) {
      return takeNotes(sessionId, (n) => !n.consumed, (n) => (n.consumed = true));
    },
  };
}
