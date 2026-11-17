"""Identity types: immutable dataclasses, nothing of the storage engine.
Instants are ISO 8601 strings with time zone, as the adapter stored them."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Role = Literal["admin", "miembro"]
ROLES: tuple[Role, ...] = ("admin", "miembro")


@dataclass(frozen=True)
class UserRow:
    id: int
    username: str
    password_hash: str
    role: Role
    notes: str
    created_at: str
    disabled_at: str | None

    @property
    def disabled(self) -> bool:
        return self.disabled_at is not None

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_active_admin(self) -> bool:
        return self.is_admin and not self.disabled


@dataclass(frozen=True)
class RefreshTokenRow:
    """The hash of a refresh token, never the token itself. It rotates on
    every use: the spent one keeps ``revoked_at`` and is not deleted."""

    id: int
    user_id: int
    token_hash: str
    issued_at: str
    expires_at: str
    revoked_at: str | None
