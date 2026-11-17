"""The composition of the ``models`` area: the switch over the Lifecycle and
what follows a successful one (the live ``cfg`` and the legacy portal)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import APIRouter

from rinthel_tui.api.adapters import Adapters
from rinthel_tui.api.models.routes import router
from rinthel_tui.config import RinthelConfig, with_local_model
from rinthel_tui.install import portal_model
from rinthel_tui.lifecycle import executor, install_tasks
from rinthel_tui.lifecycle.executor import Broadcast
from rinthel_tui.models.adapters.lifecycle_llama import LifecycleLlama
from rinthel_tui.models.domain.models import ModelSwitch
from rinthel_tui.models.domain.ports import ActiveModels, Catalog
from rinthel_tui.models.domain.types import LocalModel


@dataclass(frozen=True)
class ModelsArea:
    router: APIRouter
    catalog: Catalog
    active: ActiveModels
    switch: ModelSwitch
    # After a switch: the model llama-server now serves becomes the one of
    # the live ``cfg`` (routing, boot, reload) and of the legacy portal.
    # Returns the warnings of what could not follow.
    adopt: Callable[[LocalModel], list[str]]


def compose(
    adapters: Adapters,
    *,
    cfg_of: Callable[[], RinthelConfig],
    set_cfg: Callable[[RinthelConfig], None],
    broadcast: Broadcast,
) -> ModelsArea:
    models = adapters.models
    llama = LifecycleLlama(cfg_of, broadcast, execute=executor.bound_to(adapters.lifecycle_host))
    switch = ModelSwitch(models.catalog, models.active, {"llm": llama}, models.turns)

    def adopt(model: LocalModel) -> list[str]:
        cfg = with_local_model(cfg_of(), model)
        set_cfg(cfg)
        if not cfg.pithagoras.enabled:
            return []
        try:
            portal_model.publish(install_tasks.portal_model(cfg), adapters.lifecycle_host.host_info.platform())
        except (ValueError, OSError) as exc:
            return [f"el portal no pudo seguir al modelo nuevo: {exc}"]
        return []

    return ModelsArea(router=router, catalog=models.catalog, active=models.active, switch=switch, adopt=adopt)
