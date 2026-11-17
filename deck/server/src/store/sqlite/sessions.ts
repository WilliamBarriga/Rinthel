import type Database from "better-sqlite3";
import type { EventRow, SessionPatch, SessionRow, SessionsRepo } from "../port.js";

const PATCHABLE: readonly (keyof SessionPatch)[] = ["title", "status", "last_error", "provider", "model", "thinking_level", "pinned", "pi_session_file"];
const NOW = "strftime('%Y-%m-%d %H:%M:%S', 'now')";
/** Most recently touched first; among equals, the one inserted later. */
const NEWEST = "ORDER BY updated_at DESC, rowid DESC";
const stamp = (d: Date) => d.toISOString().slice(0, 19).replace("T", " ");

export function sqliteSessions(db: Database.Database, now?: () => Date): SessionsRepo {
  const q = {
    create: db.prepare(
      "INSERT INTO sessions (id, title, workspace, executor, kind, owner_user_id) VALUES (@id, @title, @workspace, @executor, @kind, @owner_user_id)",
    ),
    get: db.prepare("SELECT * FROM sessions WHERE id = ?"),
    listAll: db.prepare(`SELECT * FROM sessions WHERE kind = 'task' ORDER BY pinned DESC, updated_at DESC, rowid DESC`),
    listOwner: db.prepare(`SELECT * FROM sessions WHERE kind = 'task' AND owner_user_id = ? ORDER BY pinned DESC, updated_at DESC, rowid DESC`),
    listAgent: db.prepare(`SELECT * FROM sessions WHERE kind = 'agent' ${NEWEST}`),
    listOwnedBy: db.prepare("SELECT * FROM sessions WHERE owner_user_id = ?"),
    listBrowser: db.prepare(`SELECT * FROM sessions WHERE browser = 1 ${NEWEST}`),
    setBrowser: db.prepare("UPDATE sessions SET browser = ? WHERE id = ?"),
    framing: db.prepare("UPDATE sessions SET staff_framing_sent = 1 WHERE id = ?"),
    delete: db.prepare("DELETE FROM sessions WHERE id = ?"),
    orphaned: db.prepare(`UPDATE sessions SET status = 'interrupted', updated_at = ${NOW} WHERE status = 'running'`),
    append: db.prepare(`INSERT INTO events (session_id, type, payload, created_at) VALUES (?, ?, ?, coalesce(?, ${NOW})) RETURNING *`),
    hasEvent: db.prepare("SELECT 1 FROM events WHERE session_id = ? AND type = ? LIMIT 1"),
    replayStart: db.prepare("SELECT seq FROM events WHERE session_id = ? ORDER BY seq DESC LIMIT 1 OFFSET ?"),
    before: db.prepare("SELECT * FROM (SELECT * FROM events WHERE session_id = ? AND seq < ? ORDER BY seq DESC LIMIT ?) ORDER BY seq ASC"),
    since: db.prepare("SELECT * FROM events WHERE session_id = ? AND seq > ? ORDER BY seq ASC LIMIT ?"),
    prune: db.prepare("DELETE FROM events WHERE created_at < ?"),
    addNote: db.prepare("INSERT INTO notes (session_id, text, pending_delivery) VALUES (?, ?, ?)"),
    takeDeliveries: db.prepare("UPDATE notes SET pending_delivery = 0 WHERE session_id = ? AND pending_delivery = 1 RETURNING id, text"),
    takeNotes: db.prepare(`UPDATE notes SET consumed_at = ${NOW} WHERE session_id = ? AND consumed_at IS NULL RETURNING id, text`),
  };
  /** `RETURNING` gives no order: oldest first is by id. */
  const texts = (rows: unknown[]) => (rows as { id: number; text: string }[]).sort((a, b) => a.id - b.id).map((r) => r.text);

  return {
    async create(row) {
      q.create.run({ id: row.id, title: row.title, workspace: row.workspace, executor: row.executor, kind: row.kind ?? "task", owner_user_id: row.owner_user_id ?? null });
    },
    async get(id) {
      return q.get.get(id) as SessionRow | undefined;
    },
    async list(ownerUserId) {
      return (ownerUserId === undefined ? q.listAll.all() : q.listOwner.all(ownerUserId)) as SessionRow[];
    },
    async listAgent() {
      return q.listAgent.all() as SessionRow[];
    },
    async listOwnedBy(ownerUserId) {
      return q.listOwnedBy.all(ownerUserId) as SessionRow[];
    },
    async listBrowserEnabled() {
      return q.listBrowser.all() as SessionRow[];
    },
    async update(id, patch) {
      const fields = PATCHABLE.filter((k) => k in patch);
      if (!fields.length) return;
      // The column names come from the fixed list above, never from the caller.
      const sets = fields.map((k) => `${k} = @${k}`).join(", ");
      const values = Object.fromEntries(fields.map((k) => [k, patch[k] ?? null]));
      db.prepare(`UPDATE sessions SET ${sets}, updated_at = ${NOW} WHERE id = @id`).run({ ...values, id });
    },
    async setBrowser(id, on) {
      q.setBrowser.run(on ? 1 : 0, id);
    },
    async markStaffFramingSent(id) {
      q.framing.run(id);
    },
    async delete(id) {
      q.delete.run(id);
    },
    async markOrphanedInterrupted() {
      return q.orphaned.run().changes;
    },
    async appendEvent(sessionId, type, payload) {
      return q.append.get(sessionId, type, JSON.stringify(payload), now ? stamp(now()) : null) as EventRow;
    },
    async hasEvent(sessionId, type) {
      return q.hasEvent.get(sessionId, type) !== undefined;
    },
    async replayStart(sessionId, keep) {
      return (q.replayStart.get(sessionId, keep) as { seq: number } | undefined)?.seq ?? 0;
    },
    async eventsBefore(sessionId, before, limit = 1500) {
      return q.before.all(sessionId, before, limit) as EventRow[];
    },
    async eventsSince(sessionId, since = 0, limit = 5000) {
      return q.since.all(sessionId, since, limit) as EventRow[];
    },
    async pruneEvents(before) {
      return q.prune.run(stamp(before)).changes;
    },
    async addNote(sessionId, text, pendingDelivery = false) {
      q.addNote.run(sessionId, text, pendingDelivery ? 1 : 0);
    },
    async takeDeliveries(sessionId) {
      return texts(q.takeDeliveries.all(sessionId));
    },
    async takeNotes(sessionId) {
      return texts(q.takeNotes.all(sessionId));
    },
  };
}
