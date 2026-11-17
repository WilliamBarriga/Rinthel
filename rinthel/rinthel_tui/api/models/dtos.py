"""The DTOs of the ``models`` area. Deck mirrors them by hand (ADR 0001: no
codegen)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from rinthel_tui.api.lifecycle.dtos import ServiceOutcome


class CapabilityRoute(BaseModel):
    url: str
    model: str
    context_window: int
    reasoning_format: str


class Routing(BaseModel):
    # Only the Capabilities with an active Local model that can run.
    capabilities: dict[str, CapabilityRoute]
    # Where Deck reaches Understory (Memoria); None when it is off.
    understory_url: str | None


class ModelEntry(BaseModel):
    id: str
    name: str | None
    capability: str | None
    activable: bool
    problem: str | None
    context_window: int | None
    reasoning_format: str | None


class ModelListing(BaseModel):
    active: dict[str, str | None]
    models: list[ModelEntry]


class ActivateRequest(BaseModel):
    id: str = Field(min_length=1)


class OffRequest(BaseModel):
    # Only voice turns off; ``llm`` changes model but is never off.
    capability: Literal["stt", "tts"]


class ActivateResult(BaseModel):
    ok: bool
    active: str | None
    # None: nothing had to be restored (the switch worked, or there was no
    # previous model to go back to).
    rolled_back: bool | None
    results: list[ServiceOutcome]
    warnings: list[str] = []
