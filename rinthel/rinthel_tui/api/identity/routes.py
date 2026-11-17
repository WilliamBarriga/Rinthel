"""Identity over HTTP. Login, refresh and logout are ``public`` (that is how a
Panel token is obtained); user administration is ``admin`` (only the admin
edits users, their own password included; a member has no self-service);
``session-principal`` is ``service_as_user``, the one route Deck calls to
read a user's live role.

The first admin is not created here: INSTALL creates it
(``phase_install_identity``) and ``reset-admin`` recovers it, both against
``Identity`` directly."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from rinthel_tui.api.access import admin, public, service_as_user
from rinthel_tui.api.deps import state
from rinthel_tui.api.errors import ErrorTable, Reply, coded
from rinthel_tui.api.identity.dtos import (
    LoginRequest,
    LoginSession,
    LogoutRequest,
    OkResult,
    RefreshRequest,
    SessionPrincipal,
    SessionUser,
    UserCreate,
    UserPublic,
    UsersList,
    UserUpdate,
)
from rinthel_tui.clock import Clock
from rinthel_tui.config import RinthelConfig
from rinthel_tui.identity import tokens
from rinthel_tui.identity.domain import users
from rinthel_tui.identity.domain.errors import (
    IdentityUnavailable,
    LastAdmin,
    SelfLockout,
    SessionsNotRetired,
    UsernameTaken,
)
from rinthel_tui.identity.domain.ports import DeckSessions, Identity
from rinthel_tui.identity.domain.types import UserRow

ERRORS: ErrorTable = {
    UsernameTaken: lambda exc: Reply(409, {"code": "username_taken", "message": f"username {exc} already exists"}),
    SelfLockout: coded(409, "self_lockout"),
    LastAdmin: coded(409, "last_admin"),
    SessionsNotRetired: coded(502, "sessions_not_retired"),
    IdentityUnavailable: Reply(503, "identity unavailable"),
}

_cfg = state("cfg")
_clock = state("clock")
_identity = state("identity")
_deck_sessions = state("deck_sessions")

router = APIRouter()


def _public(user: UserRow) -> UserPublic:
    return UserPublic(
        id=user.id, username=user.username, role=user.role, notes=user.notes, created_at=user.created_at,
        disabled=user.disabled,
    )


def _issue_session(cfg: RinthelConfig, identity: Identity, user: UserRow, now: datetime) -> LoginSession:
    if not cfg.secrets.panel:
        # An empty secret would sign tokens anyone can forge.
        raise HTTPException(503, "RINTHEL_PANEL_SECRET is not set: run INSTALL")
    ttl = cfg.identity.access_ttl_seconds
    access = tokens.issue_access_token(
        secret=cfg.secrets.panel, user_id=user.id, username=user.username, role=user.role, ttl_seconds=ttl, now=now
    )
    refresh = tokens.new_refresh_token()
    identity.store_refresh_token(
        user_id=user.id,
        token_hash=tokens.hash_refresh_token(refresh),
        expires_at=tokens.refresh_expiry(cfg.identity.refresh_ttl_seconds, now=now),
    )
    return LoginSession(
        access_token=access,
        refresh_token=refresh,
        access_expires_in=ttl,
        user=SessionUser(id=user.id, username=user.username, role=user.role),
    )


@router.post("/identity/login", response_model=LoginSession, dependencies=[Depends(public)])
def identity_login(
    payload: LoginRequest,
    cfg: RinthelConfig = Depends(_cfg),
    identity: Identity = Depends(_identity),
    clock: Clock = Depends(_clock),
) -> LoginSession:
    user = identity.get_user_by_username(payload.username)
    if user is None or user.disabled or not tokens.verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "invalid credentials")
    return _issue_session(cfg, identity, user, clock.now())


@router.post("/identity/refresh", response_model=LoginSession, dependencies=[Depends(public)])
def identity_refresh(
    payload: RefreshRequest,
    cfg: RinthelConfig = Depends(_cfg),
    identity: Identity = Depends(_identity),
    clock: Clock = Depends(_clock),
) -> LoginSession:
    """Single use: the token presented is revoked and the one returned is
    the only valid one from now on."""
    now = clock.now()
    token_hash = tokens.hash_refresh_token(payload.refresh_token)
    row = identity.get_refresh_token(token_hash)
    if row is None or row.revoked_at is not None or tokens.is_expired(row.expires_at, now=now):
        raise HTTPException(401, "invalid refresh token")
    user = identity.get_user(row.user_id)
    if user is None or user.disabled:
        raise HTTPException(401, "invalid refresh token")
    identity.revoke_refresh_token(token_hash)
    return _issue_session(cfg, identity, user, now)


@router.post("/identity/logout", response_model=OkResult, dependencies=[Depends(public)])
def identity_logout(payload: LogoutRequest, identity: Identity = Depends(_identity)) -> OkResult:
    if payload.refresh_token:
        identity.revoke_refresh_token(tokens.hash_refresh_token(payload.refresh_token))
    return OkResult(ok=True)


@router.get("/identity/me/session-principal", response_model=SessionPrincipal)
def identity_session_principal(acting: UserRow = Depends(service_as_user)) -> SessionPrincipal:
    """Deck reads the owner and live role before authorizing a Session or
    an admin route of its own; disabled or deleted is the policy's 401."""
    return SessionPrincipal(user_id=acting.id, role=acting.role)


@router.get("/identity/users", response_model=UsersList, dependencies=[Depends(admin)])
def identity_list_users(identity: Identity = Depends(_identity)) -> UsersList:
    return UsersList(users=[_public(u) for u in identity.list_users()])


@router.post("/identity/users", response_model=UserPublic, dependencies=[Depends(admin)])
def identity_create_user(payload: UserCreate, identity: Identity = Depends(_identity)) -> UserPublic:
    user = identity.create_user(
        username=payload.username,
        password_hash=tokens.hash_password(payload.password),
        role=payload.role,
        notes=payload.notes,
    )
    return _public(user)


@router.patch("/identity/users/{user_id}", response_model=UserPublic)
def identity_update_user(
    user_id: int,
    payload: UserUpdate,
    acting: UserRow = Depends(admin),
    identity: Identity = Depends(_identity),
) -> UserPublic:
    user = users.update_user(
        identity,
        acting.id,
        user_id,
        role=payload.role,
        notes=payload.notes,
        disabled=payload.disabled,
        password_hash=tokens.hash_password(payload.password) if payload.password is not None else None,
    )
    if user is None:
        raise HTTPException(404, "not found")
    return _public(user)


@router.delete("/identity/users/{user_id}", response_model=OkResult)
def identity_delete_user(
    user_id: int,
    acting: UserRow = Depends(admin),
    identity: Identity = Depends(_identity),
    sessions: DeckSessions | None = Depends(_deck_sessions),
) -> OkResult:
    """Deck retires the user's Sessions first; if it fails, 502 and the user
    stays. A user that does not exist is already gone: ``ok``."""
    users.delete_user(identity, sessions, acting.id, user_id)
    return OkResult(ok=True)
