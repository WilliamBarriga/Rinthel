"""The composition of the ``models`` area: the switch over the Lifecycle and
what follows a successful one (the live ``cfg``)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import APIRouter

from rinthel_tui.api.adapters import Adapters
from rinthel_tui.api.models.routes import router
from rinthel_tui.config import RinthelConfig, with_local_model, without_model
from rinthel_tui.lifecycle import executor
from rinthel_tui.lifecycle.executor import Broadcast
from rinthel_tui.models.adapters.lifecycle_service import LifecycleModelService
from rinthel_tui.models.domain.models import ModelSwitch
from rinthel_tui.models.domain.ports import ActiveModels, Catalog
from rinthel_tui.models.domain.types import CAPABILITIES, Capability, LocalModel


@dataclass(frozen=True)
class ModelsArea:
    router: APIRouter
    catalog: Catalog
    active: ActiveModels
    switch: ModelSwitch
    # After a switch: the model the managed service now serves becomes the
    # one of the live ``cfg`` (routing, boot, reload). Returns the warnings
    # of what could not follow.
    adopt: Callable[[LocalModel], list[str]]
    # After ``off``: the Capability leaves the live ``cfg``.
    drop: Callable[[Capability], None]


def compose(
    adapters: Adapters,
    *,
    cfg_of: Callable[[], RinthelConfig],
    set_cfg: Callable[[RinthelConfig], None],
    broadcast: Broadcast,
) -> ModelsArea:
    models = adapters.models
    execute = executor.bound_to(adapters.lifecycle_host)
    services = {
        capability: LifecycleModelService(capability, cfg_of, broadcast, execute=execute) for capability in CAPABILITIES
    }
    switch = ModelSwitch(models.catalog, models.active, services, models.turns)

    def adopt(model: LocalModel) -> list[str]:
        set_cfg(with_local_model(cfg_of(), model))
        return []

    def drop(capability: Capability) -> None:
        set_cfg(without_model(cfg_of(), capability))

    return ModelsArea(
        router=router, catalog=models.catalog, active=models.active, switch=switch, adopt=adopt, drop=drop,
    )
