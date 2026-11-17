"""The ports of identity. ``Identity`` has a SQLite adapter and an in-memory
one, ``DeckSessions`` an HTTP adapter and an in-memory one; each pair passes
the same contract suite (``tests/identity/test_*_contract.py``).

Outside a transaction every ``Identity`` call is its own; inside
``transaction()`` they are saved together or not at all, and no other writer
gets in until it ends (the last-admin guard counts there)."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from rinthel_tui.identity.domain.types import RefreshTokenRow, Role, UserRow


class IdentityTx(Protocol):
    # ── Users ────────────────────────────────────────────────────────────

    def create_user(self, *, username: str, password_hash: str, role: Role, notes: str = "") -> UserRow:
        """Raises ``UsernameTaken`` if the ``username`` exists."""
        ...

    def get_user(self, user_id: int) -> UserRow | None: ...

    def get_user_by_username(self, username: str) -> UserRow | None: ...

    def list_users(self) -> list[UserRow]:
        """By ``username``."""
        ...

    def has_admin(self) -> bool:
        """Whether some admin is not disabled."""
        ...

    def count_active_admins(self, *, excluding: int | None = None) -> int:
        """Admins not disabled, not counting ``excluding``."""
        ...

    def update_user(
        self, user_id: int, *, role: Role | None = None, notes: str | None = None, disabled: bool | None = None
    ) -> UserRow | None:
        """Changes only what is passed; ``None`` if the user does not exist."""
        ...

    def set_password(self, user_id: int, password_hash: str) -> None: ...

    def delete_user(self, user_id: int) -> None:
        """Takes their refresh tokens with them."""
        ...

    # ── Refresh tokens ───────────────────────────────────────────────────

    def store_refresh_token(self, *, user_id: int, token_hash: str, expires_at: str) -> None: ...

    def get_refresh_token(self, token_hash: str) -> RefreshTokenRow | None: ...

    def revoke_refresh_token(self, token_hash: str) -> None: ...

    def revoke_all_refresh_tokens_for_user(self, user_id: int) -> None: ...


class Identity(IdentityTx, Protocol):
    def transaction(self) -> AbstractContextManager[IdentityTx]: ...


class DeckSessions(Protocol):
    """The one call the daemon makes to Deck: before deleting a user."""

    def retire_user_sessions(self, user_id: int) -> int:
        """Deletes every Session of ``user_id`` in Deck and returns how many.
        Idempotent: with none it returns 0, and repeating it finishes what a
        failed call left. ``DeckSessionsError`` if Deck does not answer,
        answers 5xx or refuses."""
        ...
