"""Los comandos de lifecycle que expone el daemon (boot, terminate, reload,
install): cada uno corre su Lifecycle plan (``specs.py``) con
``executor.execute``, bloqueante, y devuelve un ``UnitOutcome`` por unidad
como única fuente de verdad. La failure policy (boot/reload/install cortan en
el primer fallo; terminate sigue con lo que queda) es del plan. El progreso
viaja aparte, por ``broadcast`` (``phase_status``/``phase_log``/``phase_batch``).

Un solo comando a la vez: el ``LifecycleLock`` de la app lo comparten estos
comandos y el cambio de Local model; quien llega con el lock tomado recibe
``LifecycleBusy`` en vez de esperar."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from rinthel_tui.config import RinthelConfig
from rinthel_tui.lifecycle import specs
from rinthel_tui.lifecycle.domain.types import UnitOutcome
from rinthel_tui.lifecycle.executor import Broadcast, Execute
from rinthel_tui.lifecycle.service_defs import LocalProcessService


class LifecycleBusy(Exception):
    """Otro comando de lifecycle (o un cambio de Local model) está corriendo."""


class LifecycleLock:
    """El lock global de la app: boot, terminate, reload, install y el cambio
    de Local model se excluyen entre sí. No encola: ``hold`` levanta
    ``LifecycleBusy`` si ya está tomado."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def hold(self) -> AsyncIterator[None]:
        if self._lock.locked():
            raise LifecycleBusy()
        async with self._lock:
            yield


class Lifecycle:
    """Lo que llaman las rutas de lifecycle (``api/lifecycle/routes.py``):
    elige el plan de cada comando. ``execute`` lo da la composición
    (``executor.bound_to`` sobre el ``Host``); los tests inyectan uno propio."""

    def __init__(
        self, cfg: RinthelConfig, broadcast: Broadcast, *, execute: Execute, lock: LifecycleLock | None = None
    ) -> None:
        self._cfg = cfg
        self._broadcast = broadcast
        self._execute = execute
        self._lock = lock or LifecycleLock()

    async def _run(self, plan: specs.Plan) -> list[UnitOutcome]:
        async with self._lock.hold():
            return await self._execute(plan, self._broadcast)

    async def boot(self) -> list[UnitOutcome]:
        return await self._run(specs.boot_plan(self._cfg))

    async def terminate(self) -> list[UnitOutcome]:
        return await self._run(specs.terminate_plan(self._cfg))

    async def reload(self) -> list[UnitOutcome]:
        return await self._run(specs.reload_plan(self._cfg))

    async def install(self, *, voice: bool = False) -> list[UnitOutcome]:
        return await self._run(specs.install_plan(self._cfg, voice=voice))

    async def restart(self, service: LocalProcessService) -> list[UnitOutcome]:
        """El cambio de Local model (``specs.restart_plan``). Sin tomar el
        lock: quien cambia ya lo tiene para el cambio entero, rollback
        incluido."""
        return await self._execute(specs.restart_plan(self._cfg, service), self._broadcast)

    async def stop(self, service: LocalProcessService) -> list[UnitOutcome]:
        """Apagar una Capability (``specs.stop_plan``), sin tomar el lock: lo
        tiene quien apaga."""
        return await self._execute(specs.stop_plan(self._cfg, service), self._broadcast)
