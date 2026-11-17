"""The composition of Local models: the adapters the daemon plugs
into the catalog, the active model and the turns in flight. ``real`` is the
only place that picks the real ones; the managed service adapter needs the
app's broadcast and is built by the ``models`` area."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from rinthel_tui.config import RinthelConfig
from rinthel_tui.models.adapters.json_catalog import JsonCatalog
from rinthel_tui.models.adapters.llama_slots import LlamaSlotsTurns
from rinthel_tui.models.adapters.toml_active import TomlActiveModels
from rinthel_tui.models.domain.ports import ActiveModels, Catalog, Turns


@dataclass(frozen=True)
class ModelAdapters:
    catalog: Catalog
    active: ActiveModels
    turns: Turns

    @classmethod
    def real(cls, cfg_of: Callable[[], RinthelConfig]) -> ModelAdapters:
        instance = cfg_of().instance
        return cls(
            catalog=JsonCatalog(instance.models_catalog_path),
            active=TomlActiveModels(instance.instance_toml_path),
            # The daemon asks llama-server on the host itself, not through
            # the address it gives Deck.
            turns=LlamaSlotsTurns(lambda: f"http://127.0.0.1:{cfg_of().llama.port}"),
        )
