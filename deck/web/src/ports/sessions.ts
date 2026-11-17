import type { AgentSessionList, PromptAccepted, Session, SessionConfig, SessionEvent, Workspace, WorkspaceList } from "@deck/contract";

/** What a Session's event stream hands its listener: a row, or the server's signal that a replay starts again. */
export type StreamEvent = SessionEvent | { type: "live-reset" };

export interface EventSubscription {
  close(): void;
}

/**
 * Port: the reader's Sessions (`/api/sessions`, `/api/agent/sessions`, `/api/workspaces`). A member
 * sees only their own; an admin all. Failures reject with a `PortError`; a Turn that cannot start
 * (an owner gone, no Local model) is the server's refusal, with its message.
 *
 * `events` follows a Session's stream: the stored history, then what happens live. It reconnects on
 * its own; the listener may get a stored event twice and has to skip it by `seq`.
 */
export interface SessionsApi {
  listTask(): Promise<Session[]>;
  listAgent(): Promise<AgentSessionList>;
  listWorkspaces(): Promise<WorkspaceList>;
  createWorkspace(name: string): Promise<Workspace>;
  createTask(workspace: string, title?: string): Promise<Session>;
  createAgent(title?: string): Promise<Session>;
  get(id: string): Promise<Session>;
  remove(id: string): Promise<void>;
  prompt(id: string, message: string): Promise<PromptAccepted>;
  abort(id: string): Promise<void>;
  config(id: string): Promise<SessionConfig>;
  answerDialog(id: string, dialog: string, answer: { value?: unknown; cancelled?: boolean }): Promise<void>;
  events(id: string, onEvent: (event: StreamEvent) => void): EventSubscription;
}
