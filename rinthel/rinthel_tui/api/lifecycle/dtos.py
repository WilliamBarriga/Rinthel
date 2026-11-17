"""Los DTOs del área lifecycle, junto a su router. El cliente Rust los espeja a
mano (ADR 0001: sin codegen)."""

from __future__ import annotations

from pydantic import BaseModel


# ── ServiceOutcome: resultado de cada unidad en boot/terminate/reload/install ──
class ServiceOutcome(BaseModel):
    service: str
    ok: bool
    message: str
