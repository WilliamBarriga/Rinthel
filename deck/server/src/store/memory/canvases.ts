import { CANVAS_KINDS, type CanvasesRepo } from "../port.js";
import { ConstraintViolation, mustExist, type MemoryState } from "./state.js";

export function memoryCanvases(state: MemoryState): CanvasesRepo {
  const { canvases } = state;
  return {
    async insert(c) {
      mustExist(state, c.session_id);
      if (!CANVAS_KINDS.includes(c.kind)) throw new ConstraintViolation(`canvas kind ${c.kind} unknown`);
      if (canvases.has(c.id)) throw new ConstraintViolation(`canvas ${c.id} exists`);
      canvases.set(c.id, { ...c });
    },

    async update(c) {
      if (canvases.get(c.id)?.session_id === c.session_id) canvases.set(c.id, { ...c });
    },

    async get(sessionId, id) {
      const c = canvases.get(id);
      return c?.session_id === sessionId ? { ...c } : undefined;
    },

    async list(sessionId) {
      return [...canvases.values()].filter((c) => c.session_id === sessionId).map((c) => ({ ...c }));
    },

    async delete(sessionId, id) {
      if (canvases.get(id)?.session_id === sessionId) canvases.delete(id);
    },

    async interruptActiveWrites() {
      for (const c of canvases.values()) {
        if (c.active_call !== null) Object.assign(c, { active_call: null, status: "interrupted" });
      }
    },
  };
}
