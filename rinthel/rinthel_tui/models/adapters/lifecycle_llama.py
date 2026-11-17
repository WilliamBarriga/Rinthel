"""``ModelService`` of ``llm`` over the Lifecycle: ``restart`` runs the llama
restart plan (kill, spawn, wait ready, each one required) with the live
``cfg`` and ``model`` as its Local model, and turns the outcomes into a
``ServiceRun``. Progress travels by ``broadcast`` like any other plan.

``execute`` comes from the composition (``executor.bound_to`` over the
``Host``); the tests run it over the ``Host`` of doubles."""

from __future__ import annotations

from collections.abc import Callable

from rinthel_tui.config import RinthelConfig, with_local_model
from rinthel_tui.lifecycle.commands import Lifecycle
from rinthel_tui.lifecycle.executor import Broadcast, Execute
from rinthel_tui.models.domain.types import LocalModel, ServiceRun


class LifecycleLlama:
    def __init__(self, cfg_of: Callable[[], RinthelConfig], broadcast: Broadcast, *, execute: Execute) -> None:
        self._cfg_of = cfg_of
        self._broadcast = broadcast
        self._execute = execute

    async def restart(self, model: LocalModel) -> ServiceRun:
        cfg = with_local_model(self._cfg_of(), model)
        if not cfg.llama.enabled:
            return ServiceRun(True, ("llama-server deshabilitado: el modelo queda activo para el próximo boot",))
        outcomes = await Lifecycle(cfg, self._broadcast, execute=self._execute).restart_llama()
        return ServiceRun(all(o.ok for o in outcomes), tuple(o.message for o in outcomes))
