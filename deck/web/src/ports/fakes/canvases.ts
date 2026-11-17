import type { Canvas, CanvasAction, CanvasActionResult, CanvasStreamMessage } from "@deck/contract";
import { PortError } from "../http-errors";
import type { CanvasesApi } from "../canvases";

export interface FakeCanvasesApi extends CanvasesApi {
  /** Makes the next call to `list` or `act` reject with `error`. */
  failNext(op: "list" | "act", error: Error): void;
  /** How many times `list` was asked. */
  readonly listCalls: number;
  /** What the Agente wrote: stores a Canvas in a Sesión (replacing the one with its id), newest first, and streams it as an `update`. */
  write(canvas: Canvas, type?: "create" | "update" | "focus"): void;
  /** Sends a message to whoever follows the stream of a Sesión, as the server would. */
  emit(sessionId: string, message: CanvasStreamMessage): void;
  /** How many followers a Sesión's stream has right now. */
  followers(sessionId: string): number;
  /** Every action asked, in order. */
  readonly actions: { sessionId: string; canvasId: string; action: CanvasAction }[];
  /** What «ask the agent» left in a Sesión. */
  readonly notes: { sessionId: string; text: string }[];
}

const NOW = "2026-01-01T00:00:00Z";

/** A Canvas with sensible defaults, for tests and for the fake's own seed. */
export function canvasFixture(over: Partial<Canvas> & { id: string }): Canvas {
  return {
    session_id: "s1",
    kind: "markdown",
    title: "Untitled document",
    content: "",
    revision: 1,
    status: "idle",
    active_call: null,
    updated_at: NOW,
    persisted: false,
    ...over,
  };
}

/**
 * In-memory Canvases: `list` answers the ones of that Sesión, newest write first, and a Sesión
 * the server does not know is `404` like the real route. Seed with the Canvases that exist.
 */
export function fakeCanvasesApi({ canvases = [], sessions }: { canvases?: Canvas[]; sessions?: string[] } = {}): FakeCanvasesApi {
  const rows = [...canvases];
  const known = () => new Set(sessions ?? rows.map((c) => c.session_id));
  const failures = new Map<string, Error>();
  const listeners = new Map<string, Set<(message: CanvasStreamMessage) => void>>();
  let listCalls = 0;
  const actions: FakeCanvasesApi["actions"] = [];
  const notes: { sessionId: string; text: string }[] = [];
  const fail = (op: string) => {
    const error = failures.get(op);
    if (!error) return;
    failures.delete(op);
    throw error;
  };
  const api: FakeCanvasesApi = {
    actions,
    notes,
    get listCalls() {
      return listCalls;
    },
    async list(sessionId) {
      listCalls++;
      fail("list");
      if (!known().has(sessionId)) throw new PortError("http", 404, "Session not found");
      return structuredClone(rows.filter((c) => c.session_id === sessionId));
    },
    stream(sessionId, onMessage) {
      const set = listeners.get(sessionId) ?? new Set();
      listeners.set(sessionId, set);
      set.add(onMessage);
      // Every connection starts with a snapshot, like the server.
      onMessage({ type: "snapshot", canvases: structuredClone(rows.filter((c) => c.session_id === sessionId)) });
      return { close: () => void set.delete(onMessage) };
    },
    async act(sessionId, canvasId, action): Promise<CanvasActionResult> {
      fail("act");
      if (!rows.some((c) => c.session_id === sessionId && c.id === canvasId)) throw new PortError("http", 404, "Canvas not found in this session");
      actions.push({ sessionId, canvasId, action: structuredClone(action) });
      const text = action.params.message.trim();
      if (!text) throw new PortError("http", 400, "Acción askAgent: the message is empty");
      notes.push({ sessionId, text });
      return { kind: "asked" };
    },
    emit(sessionId, message) {
      for (const fn of listeners.get(sessionId) ?? []) fn(structuredClone(message));
    },
    followers: (sessionId) => listeners.get(sessionId)?.size ?? 0,
    write(canvas, type = "update") {
      const at = rows.findIndex((c) => c.id === canvas.id);
      if (at >= 0) rows.splice(at, 1);
      rows.unshift(structuredClone(canvas));
      api.emit(canvas.session_id, { type, canvas });
    },
    failNext(op, error) {
      failures.set(op, error);
    },
  };
  return api;
}
