import type { SessionTaintRepo } from "../port.js";
import { mustExist, type MemoryState } from "./state.js";

export function memorySessionTaint(state: MemoryState): SessionTaintRepo {
  return {
    async isTainted(sessionId) {
      return state.tainted.has(sessionId);
    },
    async markTainted(sessionId) {
      mustExist(state, sessionId);
      state.tainted.add(sessionId);
    },
  };
}
