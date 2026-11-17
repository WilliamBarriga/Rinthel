import type Database from "better-sqlite3";
import type { CanvasesRepo, CanvasRecord } from "../port.js";

const COLUMNS = "id, session_id, kind, title, content, revision, status, active_call, updated_at";

export function sqliteCanvases(db: Database.Database): CanvasesRepo {
  const insert = db.prepare(`INSERT INTO canvases (${COLUMNS}) VALUES (@id, @session_id, @kind, @title, @content, @revision, @status, @active_call, @updated_at)`);
  const update = db.prepare(
    `UPDATE canvases SET kind = @kind, title = @title, content = @content, revision = @revision, status = @status,
       active_call = @active_call, updated_at = @updated_at WHERE id = @id AND session_id = @session_id`,
  );
  const get = db.prepare(`SELECT ${COLUMNS} FROM canvases WHERE session_id = ? AND id = ?`);
  const list = db.prepare(`SELECT ${COLUMNS} FROM canvases WHERE session_id = ? ORDER BY rowid`);
  const remove = db.prepare("DELETE FROM canvases WHERE session_id = ? AND id = ?");
  const interrupt = db.prepare("UPDATE canvases SET active_call = NULL, status = 'interrupted' WHERE active_call IS NOT NULL");
  return {
    async insert(canvas) {
      insert.run(canvas);
    },
    async update(canvas) {
      update.run(canvas);
    },
    async get(sessionId, id) {
      return get.get(sessionId, id) as CanvasRecord | undefined;
    },
    async list(sessionId) {
      return list.all(sessionId) as CanvasRecord[];
    },
    async delete(sessionId, id) {
      remove.run(sessionId, id);
    },
    async interruptActiveWrites() {
      interrupt.run();
    },
  };
}
