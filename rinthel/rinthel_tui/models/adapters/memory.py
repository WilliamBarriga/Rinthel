"""The in-memory doubles of the Local model ports: each injects
failures with ``fail_next(op, exc)``."""

from __future__ import annotations

from rinthel_tui.faults import FailNext
from rinthel_tui.models.domain.types import Capability, CatalogEntry


class InMemoryCatalog(FailNext):
    def __init__(self, entries: list[CatalogEntry] | None = None) -> None:
        self.set_entries(entries or [])

    def set_entries(self, entries: list[CatalogEntry]) -> None:
        self._entries = list(entries)

    def entries(self) -> list[CatalogEntry]:
        return list(self._entries)


class InMemoryActiveModels(FailNext):
    def __init__(self, active: dict[Capability, str] | None = None) -> None:
        self._active: dict[Capability, str] = dict(active or {})

    def get(self, capability: Capability) -> str | None:
        return self._active.get(capability)

    def set(self, capability: Capability, model_id: str) -> None:
        self._active[capability] = model_id

    def clear(self, capability: Capability) -> None:
        self._active.pop(capability, None)


class InMemoryTurns(FailNext):
    """``busy`` is what the test says is being generated."""

    def __init__(self, busy: bool = False) -> None:
        self.busy = busy

    async def in_flight(self) -> bool:
        return self.busy
