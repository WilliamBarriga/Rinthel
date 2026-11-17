import type { PortalStore } from "../port.js";
import { memoryCanvases } from "./canvases.js";
import { memorySessions } from "./sessions.js";
import { memorySessionTaint } from "./session-taint.js";
import { memorySettings } from "./settings.js";
import { newState } from "./state.js";

/**
 * The in-memory adapter of the portal store: the same port as SQLite, held in plain maps for the
 * life of the object. For tests and for anything that needs a store without a file; nothing
 * survives `close()`.
 */
export function createMemoryStore(options: { now?: () => Date } = {}): PortalStore {
  const state = newState();
  return {
    canvases: memoryCanvases(state),
    sessions: memorySessions(state, options.now),
    settings: memorySettings(),
    sessionTaint: memorySessionTaint(state),
    async close() {},
  };
}
