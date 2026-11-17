"""The daemon's SQLite file, ``rinthel.db`` (ADR 0007): how a connection is
opened and how the schema is migrated at startup.

- **Rollback journal** (``DELETE``), never WAL: the Python on Windows ships an
  SQLite affected by the WAL-reset bug between threads, and only the daemon
  opens this file.
- **One connection per operation**, explicit autocommit, ``foreign_keys`` and
  ``busy_timeout`` set on open. Writers start with ``BEGIN IMMEDIATE``
  (``write``), so two writers queue on the file lock instead of failing
  half-way.
- **Migrations** are an ordered tuple of SQL scripts; ``PRAGMA user_version``
  counts how many are applied. Each one runs with its version bump in a single
  transaction. A file whose version is newer than the code, or an SQLite older
  than 3.37 (no ``STRICT`` tables), stops startup with a clear error before
  anything is written. No checksum drift detection.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

MIN_SQLITE = (3, 37, 0)
BUSY_TIMEOUT_MS = 5000

_IDENTITY = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'miembro')),
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    disabled_at TEXT
) STRICT;

CREATE TABLE refresh_tokens (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    issued_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT
) STRICT;

CREATE INDEX refresh_tokens_user_id ON refresh_tokens (user_id);
"""

# Append only: an applied migration is never edited.
MIGRATIONS: tuple[str, ...] = (_IDENTITY,)


class DatabaseError(Exception):
    """``rinthel.db`` cannot be used by this daemon: startup stops."""


class SqliteTooOld(DatabaseError):
    pass


class SchemaTooNew(DatabaseError):
    pass


@contextmanager
def connect(path: Path) -> Iterator[sqlite3.Connection]:
    """A fresh connection to ``path``, closed on exit. Autocommit: nothing is
    in a transaction unless ``BEGIN`` says so (see ``write``)."""
    conn = sqlite3.connect(path, autocommit=True)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = DELETE")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        yield conn
    finally:
        conn.close()


@contextmanager
def write(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """A write transaction: ``BEGIN IMMEDIATE`` takes the file's write lock
    up front, so whatever is read inside (the active-admin count) cannot
    change before ``COMMIT``. Rolls back on any exception."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def migrate(
    path: Path,
    *,
    migrations: Sequence[str] = MIGRATIONS,
    sqlite_version: tuple[int, int, int] = sqlite3.sqlite_version_info,
) -> int:
    """Brings ``path`` up to ``len(migrations)`` and returns that version.
    Creates the file (and its directory) if missing."""
    if sqlite_version < MIN_SQLITE:
        found = ".".join(map(str, sqlite_version))
        raise SqliteTooOld(f"SQLite {found} is too old: rinthel.db needs 3.37 or newer (STRICT tables)")
    path.parent.mkdir(parents=True, exist_ok=True)
    known = len(migrations)
    with connect(path) as conn:
        with write(conn):
            current = conn.execute("PRAGMA user_version").fetchone()[0]
        if current > known:
            raise SchemaTooNew(
                f"{path} has schema version {current} but this daemon knows up to {known}: "
                "it was written by a newer version, update the code instead of downgrading the data"
            )
        for version in range(current + 1, known + 1):
            with write(conn):
                conn.executescript(migrations[version - 1])
                conn.execute(f"PRAGMA user_version = {version}")
    return known
