"""The ports of Local models. The catalog and the active id are files of the
Instance; the managed service and the turns in flight are the host's."""

from __future__ import annotations

from typing import Protocol

from rinthel_tui.models.domain.types import Capability, CatalogEntry, LocalModel, ServiceRun


class Catalog(Protocol):
    """The Local models the admin declared by hand. Read-only for the daemon."""

    def entries(self) -> list[CatalogEntry]:
        """Every entry, valid or not, in file order. Raises ``CatalogUnavailable``
        only when the catalog as a whole cannot be read."""
        ...


class ActiveModels(Protocol):
    """Which Local model id is active per Capability (``instance.toml``)."""

    def get(self, capability: Capability) -> str | None: ...

    def set(self, capability: Capability, model_id: str) -> None: ...


class ModelService(Protocol):
    """The managed service that serves a Capability (``llama-server`` for
    ``llm``): stop whatever runs, start it with ``model`` and wait until it
    answers. Never raises for an operational failure: it says so in ``ok``."""

    async def restart(self, model: LocalModel) -> ServiceRun: ...


class Turns(Protocol):
    """Whether a turn is being generated right now."""

    async def in_flight(self) -> bool: ...
