import type { AgentSessionList, PromptAccepted, Session, SessionConfig, SessionEvent, SessionList, Workspace, WorkspaceList } from "@deck/contract";
import { globalFetch, requestJson, type FetchLike } from "../http-errors";
import type { SessionsApi, StreamEvent } from "../sessions";

/** The browser's `EventSource`, injected so the adapter's requests can be checked without one. */
export type EventSourceLike = (url: string) => { addEventListener(type: string, fn: (e: MessageEvent) => void): void; onmessage: ((e: MessageEvent) => void) | null; close(): void };

export const browserEventSource: EventSourceLike = (url) => new EventSource(url, { withCredentials: true });

export function fetchSessionsApi(fetchImpl: FetchLike = globalFetch, openStream: EventSourceLike = browserEventSource): SessionsApi {
  const session = (id: string) => `/api/sessions/${encodeURIComponent(id)}`;
  const post = (body: unknown) => ({ method: "POST", body: JSON.stringify(body) });
  return {
    listTask: async () => (await requestJson<SessionList>(fetchImpl, "/api/sessions")).sessions,
    listAgent: () => requestJson<AgentSessionList>(fetchImpl, "/api/agent/sessions"),
    listWorkspaces: () => requestJson<WorkspaceList>(fetchImpl, "/api/workspaces"),
    createWorkspace: (name) => requestJson<Workspace>(fetchImpl, "/api/workspaces", post({ name })),
    createTask: (workspace, title) => requestJson<Session>(fetchImpl, "/api/sessions", post({ workspace, title })),
    createAgent: (title) => requestJson<Session>(fetchImpl, "/api/agent/sessions", post({ title })),
    get: (id) => requestJson<Session>(fetchImpl, session(id)),
    async remove(id) { await requestJson(fetchImpl, session(id), { method: "DELETE" }); },
    prompt: (id, message, options) => requestJson<PromptAccepted>(fetchImpl, `${session(id)}/prompt`, post({ message, ...(options?.voice ? { voice: true } : {}) })),
    async abort(id) { await requestJson(fetchImpl, `${session(id)}/abort`, post({})); },
    config: (id) => requestJson<SessionConfig>(fetchImpl, `${session(id)}/config`),
    async answerDialog(id, dialog, answer) { await requestJson(fetchImpl, `${session(id)}/ui-response`, post({ id: dialog, ...answer })); },
    events(id, onEvent) {
      const source = openStream(`${session(id)}/events`);
      source.onmessage = (e) => {
        try { onEvent(JSON.parse(e.data) as SessionEvent); } catch { /* a frame that is not an event */ }
      };
      source.addEventListener("live-reset", () => onEvent({ type: "live-reset" } satisfies StreamEvent));
      return { close: () => source.close() };
    },
  };
}
