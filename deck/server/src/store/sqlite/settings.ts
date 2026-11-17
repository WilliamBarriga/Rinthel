import type Database from "better-sqlite3";
import type { SettingsRepo } from "../port.js";

export function sqliteSettings(db: Database.Database): SettingsRepo {
  const all = db.prepare("SELECT key, value FROM settings");
  const set = db.prepare("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value");
  const clear = db.prepare("DELETE FROM settings WHERE key = ?");
  return {
    async all() {
      return Object.fromEntries((all.all() as { key: string; value: string }[]).map((r) => [r.key, r.value]));
    },
    async set(key, value) {
      set.run(key, value);
    },
    async clear(key) {
      clear.run(key);
    },
  };
}
