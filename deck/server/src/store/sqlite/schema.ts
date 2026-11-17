/**
 * The schema of `deck.db`, one migration per version: index `i` takes the file from version `i` to
 * `i + 1` (`PRAGMA user_version`). A migration is never edited once released; a change is a new
 * entry. Tables are STRICT, and dates are text `YYYY-MM-DD HH:MM:SS` in UTC, the format the
 * PortalStore hands out.
 */
const NOW = "(strftime('%Y-%m-%d %H:%M:%S', 'now'))";

export const MIGRATIONS: readonly string[] = [
  `
  CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
  ) STRICT;

  -- Users live in the daemon's database: owner_user_id is a plain column, not a foreign key.
  -- The daemon retires a user's Sessions (POST /api/agent/retire-sessions) before deleting them.
  CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    workspace TEXT NOT NULL,
    executor TEXT NOT NULL DEFAULT 'host',
    status TEXT NOT NULL DEFAULT 'idle',
    created_at TEXT NOT NULL DEFAULT ${NOW},
    updated_at TEXT NOT NULL DEFAULT ${NOW},
    last_error TEXT,
    provider TEXT,
    model TEXT,
    thinking_level TEXT,
    pinned INTEGER NOT NULL DEFAULT 0,
    pi_session_file TEXT,
    kind TEXT NOT NULL DEFAULT 'task' CHECK (kind IN ('task', 'agent')),
    browser INTEGER NOT NULL DEFAULT 0,
    owner_user_id INTEGER,
    staff_framing_sent INTEGER NOT NULL DEFAULT 0
  ) STRICT;
  CREATE INDEX idx_sessions_owner ON sessions (owner_user_id);

  -- Every event pi emits is appended here: a browser that reconnects days later replays from its
  -- last seen seq. AUTOINCREMENT: a seq is never reused, even after the newest row is deleted.
  CREATE TABLE events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT ${NOW}
  ) STRICT;
  CREATE INDEX idx_events_session ON events (session_id, seq);
  CREATE INDEX idx_events_created ON events (created_at);

  -- What the portal said into a conversation while nobody was talking to it.
  CREATE TABLE notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT ${NOW},
    consumed_at TEXT,
    -- 1 when the person has not seen this yet: it goes out with the next reply.
    pending_delivery INTEGER NOT NULL DEFAULT 0
  ) STRICT;
  CREATE INDEX idx_notes_pending ON notes (session_id, consumed_at);

  -- A Canvas is text (markdown) or an interface (ui), written by the Agent only.
  CREATE TABLE canvases (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('markdown', 'ui')),
    title TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    revision INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'saved',
    active_call TEXT,
    updated_at TEXT NOT NULL DEFAULT ${NOW}
  ) STRICT;
  CREATE INDEX idx_canvases_session ON canvases (session_id);
  `,
  `
  -- A Session that read something untrusted (the Guard's taint): a row is the mark, kept for good.
  CREATE TABLE session_taint (
    session_id TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
    tainted_at TEXT NOT NULL DEFAULT ${NOW}
  ) STRICT;
  `,
];

/** The version a file is at once every migration this code knows has run. */
export const SCHEMA_VERSION = MIGRATIONS.length;
