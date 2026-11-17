"""``ModelService`` of a Capability over the Lifecycle: ``restart`` runs the
restart plan of its managed service (kill, spawn, wait ready, each one
required) with the live ``cfg`` and ``model`` as its Local model; ``stop``
runs the stop plan (kill by port, required). Outcomes become a
``ServiceRun``; progress travels by ``broadcast`` like any other plan.

``execute`` comes from the composition (``executor.bound_to`` over the
``Host``); the tests run it over the ``Host`` of doubles."""

from __future__ import annotations

from collections.abc import Callable

from rinthel_tui.config import RinthelConfig, with_local_model
from rinthel_tui.lifecycle.commands import Lifecycle
from rinthel_tui.lifecycle.executor import Broadcast, Execute
from rinthel_tui.lifecycle.services import MODEL_SERVICES
from rinthel_tui.lifecycle.domain.types import UnitOutcome
from rinthel_tui.models.domain.types import VOICE, Capability, LocalModel, ServiceRun


class LifecycleModelService:
    def __init__(
        self,
        capability: Capability,
        cfg_of: Callable[[], RinthelConfig],
        broadcast: Broadcast,
        *,
        execute: Execute,
    ) -> None:
        self._capability = capability
        self._service = MODEL_SERVICES[capability]
        self._cfg_of = cfg_of
        self._broadcast = broadcast
        self._execute = execute

    def unavailable(self) -> str | None:
        if self._capability in VOICE and self._cfg_of().platform != "linux":
            return "la voz es solo de Linux"
        return None

    async def restart(self, model: LocalModel) -> ServiceRun:
        cfg = with_local_model(self._cfg_of(), model)
        if not self._service.enabled_of(cfg):
            return ServiceRun(
                True, (f"{self._service.display_name} deshabilitado: el modelo queda activo para el próximo boot",),
            )
        return _run(await self._lifecycle(cfg).restart(self._service))

    async def stop(self) -> ServiceRun:
        return _run(await self._lifecycle(self._cfg_of()).stop(self._service))

    def _lifecycle(self, cfg: RinthelConfig) -> Lifecycle:
        return Lifecycle(cfg, self._broadcast, execute=self._execute)


def _run(outcomes: list[UnitOutcome]) -> ServiceRun:
    return ServiceRun(all(o.ok for o in outcomes), tuple(o.message for o in outcomes))
