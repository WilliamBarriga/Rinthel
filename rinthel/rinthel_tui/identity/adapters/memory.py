"""In-memory doubles of the identity ports. They pass the same contract
suites as the real adapters; failures are injected with ``fail_next``
(``rinthel_tui/faults.py``).

``InMemoryIdentity``: one lock for the whole store, as ``BEGIN IMMEDIATE``
takes the whole file. A transaction that exits with an exception restores
the state it found.

``InMemoryDeckSessions``: Deck as the daemon sees it, Sessions by owner."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field, replace

from rinthel_tui.clock import Clock, SystemClock
from rinthel_tui.faults import FailNext
from rinthel_tui.identity.domain.errors import DeckSessionsError, UsernameTaken
from rinthel_tui.identity.domain.types import RefreshTokenRow, Role, UserRow


@dataclass
class _State:
    users: dict[int, UserRow] = field(default_factory=dict)
    tokens: dict[str, RefreshTokenRow] = field(default_factory=dict)
    next_user: int = 1
    next_token: int = 1


class InMemoryIdentity(FailNext):
    def __init__(self, *, clock: Clock | None = None) -> None:
        self._state = _State()
        self._clock = clock or SystemClock()
        self._lock = threading.RLock()

    def _now(self) -> str:
        return self._clock.now().isoformat()

    @contextmanager
    def transaction(self) -> Iterator[InMemoryIdentity]:
        with self._lock:
            before = deepcopy(self._state)
            try:
                yield self
            except BaseException:
                self._state = before
                raise

    # ── Users ────────────────────────────────────────────────────────────

    def create_user(self, *, username: str, password_hash: str, role: Role, notes: str = "") -> UserRow:
        with self._lock:
            if self.get_user_by_username(username) is not None:
                raise UsernameTaken(username)
            user = UserRow(
                id=self._state.next_user, username=username, password_hash=password_hash, role=role,
                notes=notes, created_at=self._now(), disabled_at=None,
            )
            self._state.next_user += 1
            self._state.users[user.id] = user
            return user

    def get_user(self, user_id: int) -> UserRow | None:
        with self._lock:
            return self._state.users.get(user_id)

    def get_user_by_username(self, username: str) -> UserRow | None:
        with self._lock:
            return next((u for u in self._state.users.values() if u.username == username), None)

    def list_users(self) -> list[UserRow]:
        with self._lock:
            return sorted(self._state.users.values(), key=lambda u: u.username)

    def has_admin(self) -> bool:
        return self.count_active_admins() > 0

    def count_active_admins(self, *, excluding: int | None = None) -> int:
        with self._lock:
            return sum(1 for u in self._state.users.values() if u.is_active_admin and u.id != excluding)

    def update_user(
        self, user_id: int, *, role: Role | None = None, notes: str | None = None, disabled: bool | None = None
    ) -> UserRow | None:
        with self._lock:
            user = self._state.users.get(user_id)
            if user is None:
                return None
            changes: dict[str, object] = {}
            if role is not None:
                changes["role"] = role
            if notes is not None:
                changes["notes"] = notes
            if disabled is not None:
                changes["disabled_at"] = self._now() if disabled else None
            self._state.users[user_id] = replace(user, **changes)
            return self._state.users[user_id]

    def set_password(self, user_id: int, password_hash: str) -> None:
        with self._lock:
            user = self._state.users.get(user_id)
            if user is not None:
                self._state.users[user_id] = replace(user, password_hash=password_hash)

    def delete_user(self, user_id: int) -> None:
        with self._lock:
            self._state.users.pop(user_id, None)
            self._state.tokens = {h: t for h, t in self._state.tokens.items() if t.user_id != user_id}

    # ── Refresh tokens ───────────────────────────────────────────────────

    def store_refresh_token(self, *, user_id: int, token_hash: str, expires_at: str) -> None:
        with self._lock:
            self._state.tokens[token_hash] = RefreshTokenRow(
                id=self._state.next_token, user_id=user_id, token_hash=token_hash, issued_at=self._now(),
                expires_at=expires_at, revoked_at=None,
            )
            self._state.next_token += 1

    def get_refresh_token(self, token_hash: str) -> RefreshTokenRow | None:
        with self._lock:
            return self._state.tokens.get(token_hash)

    def revoke_refresh_token(self, token_hash: str) -> None:
        with self._lock:
            token = self._state.tokens.get(token_hash)
            if token is not None and token.revoked_at is None:
                self._state.tokens[token_hash] = replace(token, revoked_at=self._now())

    def revoke_all_refresh_tokens_for_user(self, user_id: int) -> None:
        with self._lock:
            for token_hash, token in list(self._state.tokens.items()):
                if token.user_id == user_id and token.revoked_at is None:
                    self._state.tokens[token_hash] = replace(token, revoked_at=self._now())


class InMemoryDeckSessions(FailNext):
    """``add(owner)`` opens a Session; ``refuse`` makes Deck reject the
    credential (as a 401 would). ``retire_calls`` records every request,
    including the failed ones."""

    _OPS = frozenset({"retire_user_sessions"})

    def __init__(self) -> None:
        self._sessions: dict[str, int] = {}
        self._ids = 0
        self.refuse = False
        self.retire_calls: list[int] = []

    def add(self, owner_id: int) -> str:
        self._ids += 1
        session_id = f"s{self._ids}"
        self._sessions[session_id] = owner_id
        return session_id

    def sessions_of(self, owner_id: int) -> list[str]:
        return [sid for sid, owner in self._sessions.items() if owner == owner_id]

    def retire_user_sessions(self, user_id: int) -> int:
        self.retire_calls.append(user_id)
        self._enter("retire_user_sessions")
        if self.refuse:
            raise DeckSessionsError("deck answered 401")
        gone = self.sessions_of(user_id)
        for sid in gone:
            del self._sessions[sid]
        return len(gone)
