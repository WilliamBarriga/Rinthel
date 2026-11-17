import type { Session, SessionEvent, Workspace } from "@deck/contract";
import { PortError } from "../http-errors";
import type { SessionsApi, StreamEvent } from "../sessions";

export interface FakeSessionsApi extends SessionsApi {
  /** Sends an event to whoever follows Session `id`, as the server would. */
  emit(id: string, type: string, payload: unknown, live?: boolean): void;
  /** Every prompt that got in, in order. */
  readonly prompts: { id: string; message: string; voice?: boolean }[];
  readonly aborted: string[];
  readonly answered: { id: string; dialog: string; answer: { value?: unknown; cancelled?: boolean } }[];
}

export function sessionFixture(over: Partial<Session> = {}): Session {
  return {
    id: "s1", title: "Chat", workspace: "/data/users/1/agent", executor: "host", status: "idle",
    created_at: "2026-11-01 10:00:00", updated_at: "2026-11-01 10:00:00", last_error: null, pinned: false,
    live: false, provider: null, model: null, thinking_level: null, kind: "agent", ...over,
  };
}

/**
 * In memory, answering like the server: a prompt is recorded and its turn streamed back to the
 * Session's followers (the person's message, a one-word answer, idle). `emit` adds anything else.
 */
export function fakeSessionsApi({ sessions = [] as Session[], workspaces = [] as string[], answer = "hola" } = {}): FakeSessionsApi {
  const rows = sessions.map((s) => ({ ...s }));
  const spaces = [...workspaces];
  const listeners = new Map<string, Set<(e: StreamEvent) => void>>();
  const log = new Map<string, SessionEvent[]>();
  let seq = 0;
  let next = 1;
  const find = (id: string) => {
    const row = rows.find((s) => s.id === id);
    if (!row) throw new PortError("http", 404, "Sesión no encontrada");
    return row;
  };
  const prompts: FakeSessionsApi["prompts"] = [];
  const aborted: string[] = [];
  const answered: FakeSessionsApi["answered"] = [];
  const api: FakeSessionsApi = {
    prompts, aborted, answered,
    emit(id, type, payload, live = false) {
      const event: SessionEvent = { seq: live ? -(++seq) : ++seq, type, payload };
      if (!live) log.set(id, [...(log.get(id) ?? []), event]);
      for (const fn of listeners.get(id) ?? []) fn(event);
    },
    async listTask() { return rows.filter((s) => s.kind !== "agent"); },
    async listAgent() { return { agentHome: "/data/users/1/agent", sessions: rows.filter((s) => s.kind === "agent") }; },
    async listWorkspaces() {
      return { root: "/data/workspaces", workspaces: spaces.map((name): Workspace => ({ name, path: `/data/workspaces/${name}`, isGit: false })) };
    },
    async createWorkspace(name) {
      const slug = name.toLowerCase().replace(/\s+/g, "-");
      spaces.push(slug);
      return { name: slug, path: `/data/workspaces/${slug}`, isGit: false };
    },
    async createTask(workspace, title) {
      const row = sessionFixture({ id: `task-${next++}`, title: title || workspace, workspace: `/data/workspaces/${workspace}`, kind: "task" });
      rows.push(row);
      return row;
    },
    async createAgent(title) {
      const row = sessionFixture({ id: `chat-${next++}`, title: title || "Chat" });
      rows.push(row);
      return row;
    },
    async get(id) { return { ...find(id) }; },
    async remove(id) { const at = rows.findIndex((s) => s.id === id); if (at >= 0) rows.splice(at, 1); },
    async prompt(id, message, options) {
      find(id);
      prompts.push(options?.voice ? { id, message, voice: true } : { id, message });
      const turn = `turn-${prompts.length}`;
      queueMicrotask(() => {
        api.emit(id, "portal_prompt", { message, turn_id: turn });
        api.emit(id, "portal_status", { status: "running" });
        api.emit(id, "message_end", { streamId: `m-${turn}`, message: { role: "assistant", content: [{ type: "text", text: answer }] } });
        api.emit(id, "portal_status", { status: "idle" });
      });
      return { ok: true, status: "running", queued: false, turn_id: turn };
    },
    async abort(id) { aborted.push(id); api.emit(id, "portal_status", { status: "idle", aborted: true }); },
    async config(id) {
      find(id);
      return { live: false, state: { model: { id: "", name: "sin iniciar", provider: "rinthel" }, thinkingLevel: "medium" }, thinking: { levels: [] }, stats: null };
    },
    async answerDialog(id, dialog, answer) { answered.push({ id, dialog, answer }); },
    events(id, onEvent) {
      const set = listeners.get(id) ?? new Set();
      set.add(onEvent);
      listeners.set(id, set);
      queueMicrotask(() => { onEvent({ type: "live-reset" }); for (const e of log.get(id) ?? []) onEvent(e); });
      return { close: () => set.delete(onEvent) };
    },
  };
  return api;
}
