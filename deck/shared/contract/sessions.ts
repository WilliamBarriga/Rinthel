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
