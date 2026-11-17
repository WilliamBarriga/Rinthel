"""Los DTOs del área config, junto a su router. El cliente Rust los espeja a
mano (ADR 0001: sin codegen)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


# ── Theme palette — canonical (10 colores base) ──────────────────────────────
class ThemeCanonical(BaseModel):
    fg: str
    accent: str
    electric: str
    warn: str
    success: str
    hot: str
    caution: str
    glow: str
    dim: str
    bg: str


# ── Theme palette — extendida (7 colores derivados) ───────────────────────────
class ThemeExtended(BaseModel):
    cool: str
    cool_dim: str
    hot_dim: str
    electric_dim: str
    steel: str
    steel_dim: str
    accent_dim: str


# ── GET /theme response shape ────────────────────────────────────────────────
class ThemeResponse(BaseModel):
    canonical: ThemeCanonical
    extended: ThemeExtended
    frame_chars: list[str]


# ── ConfigField: un campo dentro de un servicio en GET /config ────────────────
class ConfigField(BaseModel):
    attr: str
    env: str
    kind: str
    group: str
    value: str
    # The Validated profile's value for a hardware/cache field; ``None`` for
    # fields the profile does not cover.
    profile: str | None = None


# ── ConfigService: sub-config + toggle + campos en GET /config ───────────────
class ConfigService(BaseModel):
    attr: str
    display_name: str
    enabled: bool | None = None
    enabled_env: str | None = None
    fields: list[ConfigField]


# ── GET /config response shape ───────────────────────────────────────────────
class ConfigPayload(BaseModel):
    model_config = ConfigDict(extra="allow")
    services: list[ConfigService]


# ── POST /config request body ────────────────────────────────────────────────
class ConfigUpdate(BaseModel):
    overrides: dict[str, str] = {}


# ── POST /config response shape (apply_config_overrides) ─────────────────────
class ConfigUpdateResult(BaseModel):
    ok: bool
    written: int
    errors: list[str] | None = None
    warnings: list[str] | None = None
