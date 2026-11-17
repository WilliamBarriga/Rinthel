"""Los comandos de lifecycle que expone el daemon (boot, terminate, reload,
install): cada uno corre su Lifecycle plan (``specs.py``) con
``executor.execute``, bloqueante, y devuelve un ``UnitOutcome`` por unidad
como única fuente de verdad. La failure policy (boot/reload/install cortan en
el primer fallo; terminate sigue con lo que queda) es del plan. El progreso
viaja aparte, por ``broadcast`` (``phase_status``/``phase_log``/``phase_batch``)."""

from __future__ import annotations

from rinthel_tui.config import RinthelConfig
from rinthel_tui.lifecycle import specs
from rinthel_tui.lifecycle.domain.types import UnitOutcome
from rinthel_tui.lifecycle.executor import Broadcast, Execute


class Lifecycle:
    """Lo que llaman las rutas de lifecycle (``api/lifecycle/routes.py``):
    elige el plan de cada comando. ``execute`` lo da la composición
    (``executor.bound_to`` sobre el ``Host``); los tests inyectan uno propio."""

    def __init__(self, cfg: RinthelConfig, broadcast: Broadcast, *, execute: Execute) -> None:
        self._cfg = cfg
        self._broadcast = broadcast
        self._execute = execute

    async def boot(self) -> list[UnitOutcome]:
        return await self._execute(specs.boot_plan(self._cfg), self._broadcast)

    async def terminate(self) -> list[UnitOutcome]:
        return await self._execute(specs.terminate_plan(self._cfg), self._broadcast)

    async def reload(self) -> list[UnitOutcome]:
        return await self._execute(specs.reload_plan(self._cfg), self._broadcast)

    async def install(self) -> list[UnitOutcome]:
        return await self._execute(specs.install_plan(self._cfg), self._broadcast)
