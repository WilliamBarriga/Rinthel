"""DTOs of the identity area. Deck writes its own types for these by hand
(``shared/contract``): a change here is a change there."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from rinthel_tui.identity.domain.types import Role

Password = Annotated[str, Field(min_length=8)]
Username = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


# ── POST /identity/login, /refresh, /logout ──────────────────────────────────
class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: Annotated[str, Field(min_length=1)]


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class SessionUser(BaseModel):
    id: int
    username: str
    role: Role


class LoginSession(BaseModel):
    access_token: str
    refresh_token: str
    access_expires_in: int
    user: SessionUser


# ── GET /identity/me/session-principal ──────────────────────────────────────
class SessionPrincipal(BaseModel):
    user_id: int
    role: Role


# ── /identity/users ──────────────────────────────────────────────────────────
class UserPublic(BaseModel):
    id: int
    username: str
    role: Role
    notes: str
    created_at: str
    disabled: bool


class UsersList(BaseModel):
    users: list[UserPublic]


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: Username
    password: Password
    role: Role
    notes: str = ""


class UserUpdate(BaseModel):
    """Only what is sent changes."""

    model_config = ConfigDict(extra="forbid")

    role: Role | None = None
    notes: str | None = None
    disabled: bool | None = None
    password: Password | None = None


class OkResult(BaseModel):
    ok: bool
