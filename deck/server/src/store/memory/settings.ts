import type { SettingsRepo } from "../port.js";

export function memorySettings(): SettingsRepo {
  const values = new Map<string, string>();
  return {
    async all() {
      return Object.fromEntries(values);
    },
    async set(key, value) {
      values.set(key, value);
    },
    async clear(key) {
      values.delete(key);
    },
  };
}
