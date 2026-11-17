"""``Identity`` on ``rinthel.db`` (ADR 0007). Every call opens its own
connection (``database.connect``) and closes it: no connection is shared
between threads. A call that writes runs in ``BEGIN IMMEDIATE``;
``transaction()`` keeps one connection and one ``BEGIN IMMEDIATE`` for
everything inside it, so no other writer gets in until it ends.

The schema is the migrator's (``database.MIGRATIONS``): this adapter assumes
it is current, which the startup gate guarantees."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from rinthel_tui import database
from rinthel_tui.clock import Clock, SystemClock
from rinthel_tui.identity.domain.errors import IdentityUnavailable, UsernameTaken
from rinthel_tui.identity.domain.types import RefreshTokenRow, Role, UserRow

_USER_COLUMNS = "id, username, password_hash, role, notes, created_at, disabled_at"
_TOKEN_COLUMNS = "id, user_id, token_hash, issued_at, expires_at, revoked_at"


def _user(row: sqlite3.Row | None) -> UserRow | None:
    return None if row is None else UserRow(**dict(row))


def _token(row: sqlite3.Row | None) -> RefreshTokenRow | None:
    return None if row is None else RefreshTokenRow(**dict(row))


class _Tx:
    """The operations on one open connection; whoever builds it decides the
    transaction around them."""

    def __init__(self, conn: sqlite3.Connection, now: Callable[[], str]) -> None:
        self._conn = conn
        self._now = now

    def _one(self, sql: str, *params: Any) -> sqlite3.Row | None:
        return self._conn.execute(sql, params).fetchone()

    def create_user(self, *, username: str, password_hash: str, role: Role, notes: str = "") -> UserRow:
        try:
            row = self._one(
                f"INSERT INTO users (username, password_hash, role, notes, created_at) VALUES (?, ?, ?, ?, ?) "
                f"RETURNING {_USER_COLUMNS}",
                username, password_hash, role, notes, self._now(),
            )
        except sqlite3.IntegrityError as exc:
            if "users.username" in str(exc):
                raise UsernameTaken(username) from exc
            raise
        return _user(row)

    def get_user(self, user_id: int) -> UserRow | None:
        return _user(self._one(f"SELECT {_USER_COLUMNS} FROM users WHERE id = ?", user_id))

    def get_user_by_username(self, username: str) -> UserRow | None:
        return _user(self._one(f"SELECT {_USER_COLUMNS} FROM users WHERE username = ?", username))

    def list_users(self) -> list[UserRow]:
        rows = self._conn.execute(f"SELECT {_USER_COLUMNS} FROM users ORDER BY username").fetchall()
        return [UserRow(**dict(r)) for r in rows]

    def has_admin(self) -> bool:
        return self.count_active_admins() > 0

    def count_active_admins(self, *, excluding: int | None = None) -> int:
        row = self._one(
            "SELECT count(*) FROM users WHERE role = 'admin' AND disabled_at IS NULL AND id IS NOT ?", excluding
        )
        return row[0]

    def update_user(
        self, user_id: int, *, role: Role | None = None, notes: str | None = None, disabled: bool | None = None
    ) -> UserRow | None:
        sets: list[str] = []
        params: list[Any] = []
        if role is not None:
            sets.append("role = ?")
            params.append(role)
        if notes is not None:
            sets.append("notes = ?")
            params.append(notes)
        if disabled is not None:
            sets.append("disabled_at = ?")
            params.append(self._now() if disabled else None)
        if not sets:
            return self.get_user(user_id)
        row = self._one(f"UPDATE users SET {', '.join(sets)} WHERE id = ? RETURNING {_USER_COLUMNS}", *params, user_id)
        return _user(row)

    def set_password(self, user_id: int, password_hash: str) -> None:
        self._conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))

    def delete_user(self, user_id: int) -> None:
        # ``refresh_tokens`` goes with the row: ON DELETE CASCADE.
        self._conn.execute("DELETE FROM users WHERE id = ?", (user_id,))

    def store_refresh_token(self, *, user_id: int, token_hash: str, expires_at: str) -> None:
        self._conn.execute(
            "INSERT INTO refresh_tokens (user_id, token_hash, issued_at, expires_at) VALUES (?, ?, ?, ?)",
            (user_id, token_hash, self._now(), expires_at),
        )

    def get_refresh_token(self, token_hash: str) -> RefreshTokenRow | None:
        return _token(self._one(f"SELECT {_TOKEN_COLUMNS} FROM refresh_tokens WHERE token_hash = ?", token_hash))

    def revoke_refresh_token(self, token_hash: str) -> None:
        self._conn.execute(
            "UPDATE refresh_tokens SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL",
            (self._now(), token_hash),
        )

    def revoke_all_refresh_tokens_for_user(self, user_id: int) -> None:
        self._conn.execute(
            "UPDATE refresh_tokens SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
            (self._now(), user_id),
        )


_READS = frozenset({"get_user", "get_user_by_username", "list_users", "has_admin", "count_active_admins", "get_refresh_token"})


class SqliteIdentity:
    def __init__(self, path: Path, *, clock: Clock | None = None) -> None:
        self._path = path
        self._clock = clock or SystemClock()

    def _now(self) -> str:
        return self._clock.now().isoformat()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        """A connection whose engine failures (``busy_timeout`` spent, an
        unreadable file) come out as ``IdentityUnavailable``."""
        try:
            with database.connect(self._path) as conn:
                yield conn
        except sqlite3.IntegrityError:
            raise
        except sqlite3.Error as exc:
            raise IdentityUnavailable(str(exc)) from exc

    @contextmanager
    def transaction(self) -> Iterator[_Tx]:
        with self._connection() as conn, database.write(conn):
            yield _Tx(conn, self._now)

    def _call(self, op: str, *args: Any, **kwargs: Any) -> Any:
        if op in _READS:
            with self._connection() as conn:
                return getattr(_Tx(conn, self._now), op)(*args, **kwargs)
        with self.transaction() as tx:
            return getattr(tx, op)(*args, **kwargs)

    def create_user(self, *, username: str, password_hash: str, role: Role, notes: str = "") -> UserRow:
        return self._call("create_user", username=username, password_hash=password_hash, role=role, notes=notes)

    def get_user(self, user_id: int) -> UserRow | None:
        return self._call("get_user", user_id)

    def get_user_by_username(self, username: str) -> UserRow | None:
        return self._call("get_user_by_username", username)

    def list_users(self) -> list[UserRow]:
        return self._call("list_users")

    def has_admin(self) -> bool:
        return self._call("has_admin")

    def count_active_admins(self, *, excluding: int | None = None) -> int:
        return self._call("count_active_admins", excluding=excluding)

    def update_user(
        self, user_id: int, *, role: Role | None = None, notes: str | None = None, disabled: bool | None = None
    ) -> UserRow | None:
        return self._call("update_user", user_id, role=role, notes=notes, disabled=disabled)

    def set_password(self, user_id: int, password_hash: str) -> None:
        self._call("set_password", user_id, password_hash)

    def delete_user(self, user_id: int) -> None:
        self._call("delete_user", user_id)

    def store_refresh_token(self, *, user_id: int, token_hash: str, expires_at: str) -> None:
        self._call("store_refresh_token", user_id=user_id, token_hash=token_hash, expires_at=expires_at)

    def get_refresh_token(self, token_hash: str) -> RefreshTokenRow | None:
        return self._call("get_refresh_token", token_hash)

    def revoke_refresh_token(self, token_hash: str) -> None:
        self._call("revoke_refresh_token", token_hash)

    def revoke_all_refresh_tokens_for_user(self, user_id: int) -> None:
        self._call("revoke_all_refresh_tokens_for_user", user_id)
