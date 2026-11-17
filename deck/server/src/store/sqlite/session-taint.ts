import type Database from "better-sqlite3";
import type { SessionTaintRepo } from "../port.js";

export function sqliteSessionTaint(db: Database.Database): SessionTaintRepo {
  const get = db.prepare("SELECT 1 FROM session_taint WHERE session_id = ?");
  const mark = db.prepare("INSERT INTO session_taint (session_id) VALUES (?) ON CONFLICT (session_id) DO NOTHING");
  return {
    async isTainted(sessionId) {
      return get.get(sessionId) !== undefined;
    },
    async markTainted(sessionId) {
      mark.run(sessionId);
    },
  };
}
