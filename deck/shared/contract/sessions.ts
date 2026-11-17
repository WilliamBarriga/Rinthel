/**
 * Sesiones: what Node's `/api/sessions` and `/api/agent/sessions` tell the front.
 * Types only: the server uses them to build the answer and the front to read it.
 */

export type SessionStatus = "idle" | "running" | "error" | "interrupted";

/** `task`: opened on a workspace the person picks; `agent`: a chat in the Agent's home. */
export type SessionKind = "task" | "agent";

export interface Session {
  id: string;
  title: string;
  workspace: string;
  executor: string;
  status: SessionStatus;
  created_at: string;
  updated_at: string;
  last_error: string | null;
  pinned: boolean;
  live?: boolean;
  /** Per-session overrides, used to paint the composer pills before any fetch. */
  provider: string | null;
  model: string | null;
  thinking_level: string | null;
  kind?: SessionKind;
}

/** `GET /api/sessions`: the `task` Sessions the reader may see. */
export interface SessionList {
  sessions: Session[];
}

/** `GET /api/agent/sessions`: the reader's Agent home and the `agent` Sessions they may see. */
export interface AgentSessionList {
  agentHome: string;
  sessions: Session[];
}

/** A directory a `task` Session may work in. */
export interface Workspace {
  name: string;
  path: string;
  isGit: boolean;
}

/** `GET /api/workspaces`: the reader's workspace root and what is under it. */
export interface WorkspaceList {
  root: string;
  workspaces: Workspace[];
}
