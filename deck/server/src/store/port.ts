import type { SessionKind, SessionStatus } from "@deck/contract";

/**
 * The portal's persistence port.
 *
 * Every piece of portal state (sessions, canvases, settings) is read and written through a repo
 * here, one per aggregate. Callers never see the engine: the adapter behind it (SQLite on
 * `deck.db`) is swappable, and every method is async so a networked engine fits without touching
 * a caller.
 */

/** Portal-wide key/value settings. */
export interface SettingsRepo {
  /** Every stored key, raw: an empty value is still returned. */
  all(): Promise<Record<string, string>>;
  set(key: string, value: string): Promise<void>;
  clear(key: string): Promise<void>;
}

/**
 * What a canvas holds: `markdown` is text, `ui` the spec of an interface (as
 * JSON text in `content`). Both are written by the Agent only.
 */
export type CanvasKind = "markdown" | "ui";
export const CANVAS_KINDS: readonly CanvasKind[] = ["markdown", "ui"];

/** A canvas that has been saved. Drafts never reach the store. */
export interface CanvasRecord {
  id: string;
  session_id: string;
  kind: CanvasKind;
  title: string;
  content: string;
  revision: number;
  status: string;
  active_call: string | null;
  updated_at: string;
}

/** Saved canvases, always addressed through the session they belong to. */
export interface CanvasesRepo {
  insert(canvas: CanvasRecord): Promise<void>;
  /** Writes every field of the canvas, matched on its id and session. */
  update(canvas: CanvasRecord): Promise<void>;
  get(sessionId: string, id: string): Promise<CanvasRecord | undefined>;
  list(sessionId: string): Promise<CanvasRecord[]>;
  delete(sessionId: string, id: string): Promise<void>;
  /**
   * For boot: a write in flight died with the previous server. Marks each one
   * interrupted.
   */
  interruptActiveWrites(): Promise<void>;
}

export interface SessionRow {
  id: string;
  title: string;
  workspace: string;
  executor: string;
  status: SessionStatus;
  created_at: string;
  updated_at: string;
  last_error: string | null;
  /** Per-session overrides of the portal defaults; null means "use the default". */
  provider: string | null;
  model: string | null;
  thinking_level: string | null;
  /** A flag kept as 0 or 1; the API speaks booleans. */
  pinned: number;
  /** pi's own session file, so the exact conversation is reopened on restart. */
  pi_session_file: string | null;
  /** `task` for one opened on a workspace, `agent` for a chat in the Agent's home. */
  kind: SessionKind;
  /** May this session drive the agent's browser? Off unless turned on. */
  browser: number;
  /**
   * The user that created it: a plain column, not a foreign key. Users live in the daemon's own
   * database, a different process, so the portal cannot join them; the daemon calls
   * `POST /api/agent/retire-sessions` before it deletes a user. Null for a session created before
   * auth was individual.
   */
  owner_user_id: number | null;
  /**
   * Whether the Staff framing (name and role of the owner) has already gone into the conversation
   * once: declared at the first prompt, never again.
   */
  staff_framing_sent: number;
}

export interface EventRow {
  seq: number;
  session_id: string;
  type: string;
  payload: string;
  created_at: string;
}

export type SessionPatch = Partial<
  Pick<
    SessionRow,
    "title" | "status" | "last_error" | "provider" | "model" | "thinking_level" | "pinned" | "pi_session_file"
  >
>;

export interface NewSession {
  id: string;
  title: string;
  workspace: string;
  executor: string;
  kind?: SessionKind;
  owner_user_id?: number | null;
}

/**
 * Chat sessions, plus what hangs off one: its event log and the notes the portal
 * left in it.
 */
export interface SessionsRepo {
  create(session: NewSession): Promise<void>;
  get(id: string): Promise<SessionRow | undefined>;
  /**
   * The `task` sessions, pinned first then most recently touched. With `ownerUserId`, only that
   * owner's.
   */
  list(ownerUserId?: number): Promise<SessionRow[]>;
  /** Every session of any kind whose owner is `ownerUserId`. */
  listOwnedBy(ownerUserId: number): Promise<SessionRow[]>;
  /** The `agent` sessions, newest first. */
  listAgent(): Promise<SessionRow[]>;
  /** Sessions whose browser access is on, most recently touched first. */
  listBrowserEnabled(): Promise<SessionRow[]>;

  /** Changes the given fields and bumps `updated_at`; an empty patch does nothing. */
  update(id: string, patch: SessionPatch): Promise<void>;
  setBrowser(id: string, on: boolean): Promise<void>;
  /** The Staff framing is delivered once, never again for this session. */
  markStaffFramingSent(id: string): Promise<void>;
  /** Removes the session together with its events, notes, canvases and taint mark. */
  delete(id: string): Promise<void>;
  /**
   * For boot: a session left `running` cannot be running, its process died with
   * the previous server. Marks them interrupted and returns how many.
   */
  markOrphanedInterrupted(): Promise<number>;

  appendEvent(sessionId: string, type: string, payload: unknown): Promise<EventRow>;
  hasEvent(sessionId: string, type: string): Promise<boolean>;
  /**
   * The seq to start replaying from so a session gets its own last `keep`
   * events (0 when it has no more than that).
   */
  replayStart(sessionId: string, keep: number): Promise<number>;
  /** The page before a cursor, oldest first. */
  eventsBefore(sessionId: string, before: number, limit?: number): Promise<EventRow[]>;
  /** Events after `since`, oldest first. */
  eventsSince(sessionId: string, since?: number, limit?: number): Promise<EventRow[]>;

  /**
   * Retention: deletes the events, in every session, older than `before`, and
   * returns how many went. The sessions themselves stay.
   */
  pruneEvents(before: Date): Promise<number>;

  /** Something the portal said into a conversation, held until it next runs. */
  addNote(sessionId: string, text: string, pendingDelivery?: boolean): Promise<void>;
  /** Notes the person has not seen; taking them hands over delivery. */
  takeDeliveries(sessionId: string): Promise<string[]>;
  /** The notes waiting for the conversation, oldest first. Reading consumes them. */
  takeNotes(sessionId: string): Promise<string[]>;
}

/**
 * Whether a Session has read something untrusted, kept apart from pi's own file so a relaunch, a
 * restart of Deck or a lost pi file still starts the Session tainted. Written once, never cleared:
 * the mark goes only with its Session.
 */
export interface SessionTaintRepo {
  isTainted(sessionId: string): Promise<boolean>;
  /** Idempotent. Throws for a Session that does not exist. */
  markTainted(sessionId: string): Promise<void>;
}

export interface PortalStore {
  sessions: SessionsRepo;
  canvases: CanvasesRepo;
  settings: SettingsRepo;
  sessionTaint: SessionTaintRepo;
  close(): Promise<void>;
}
