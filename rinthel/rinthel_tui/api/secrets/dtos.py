"""Los DTOs del área secrets, junto a su router. El cliente Rust los espeja a
mano (ADR 0001: sin codegen)."""

from __future__ import annotations

from pydantic import BaseModel

from rinthel_tui.api.lifecycle.dtos import ServiceOutcome
from rinthel_tui.instance import RotatableSecret


# ── POST /secrets/rotate ─────────────────────────────────────────────────────
class SecretRotateRequest(BaseModel):
    key: RotatableSecret


class SecretRotateResult(BaseModel):
    """``service_secret`` solo si se rotó ``RINTHEL_SERVICE_SECRET``: la TUI
    no relee el ``.env``, el secreto nuevo le llega acá."""

    results: list[ServiceOutcome]
    service_secret: str | None = None
