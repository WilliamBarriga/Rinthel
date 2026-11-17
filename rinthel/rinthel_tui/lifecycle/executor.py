"""Corre un Lifecycle plan (``specs.Plan``) y devuelve un ``UnitOutcome``
por unidad — ver docs/adr/0001.

El progreso viaja por ``broadcast`` (``phase_batch`` al abrir cada tanda con
marcador, ``phase_status`` antes/después de cada fase, ``phase_log`` por
cada llamada al ``PhaseReport``). Se inyecta como argumento en vez de
conocer el ``Broadcaster`` de la app: los tests le pasan una función que
registra, sin WebSocket ni monkeypatch.

Nunca levanta por una fase: ``PhaseError`` es un fallo esperado (la fase ya
lo reportó con ``error()``); cualquier otra excepción se convierte a mano en
``ok=False`` — así un plan ``continue`` (terminate) sigue con las unidades
que quedan aunque una explote con un bug."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from rinthel_tui.lifecycle.domain.errors import PhaseError
from rinthel_tui.lifecycle.domain.host import Host
from rinthel_tui.lifecycle.domain.types import UnitOutcome
from rinthel_tui.lifecycle.specs import Plan, Unit
from rinthel_tui.monitoring.domain.envelope import MessageType

Broadcast = Callable[[MessageType, dict], Awaitable[None]]
# ``execute`` o lo que un test inyecta en su lugar.
Execute = Callable[[Plan, Broadcast], Awaitable[list[UnitOutcome]]]


@dataclass
class _Collected:
    """``PhaseReport`` de una unidad. ``info()`` queda fuera de ``messages``
    (ruido de proceso: stdout de ``docker compose``, hints) pero sí se
    transmite; success/warn/error se concatenan porque spawn y wait son
    eventos distintos y los dos aportan contexto. Las fases llaman al report
    de forma sincrónica, así que los ``phase_log`` se encolan y los manda
    ``_forward_logs`` en vivo."""

    ok: bool = True
    messages: list[str] = field(default_factory=list)
    logs: asyncio.Queue = field(default_factory=asyncio.Queue)

    def info(self, msg: str) -> None:
        self.logs.put_nowait({"kind": "info", "message": msg})

    def success(self, msg: str) -> None:
        self.messages.append(msg)
        self.logs.put_nowait({"kind": "success", "message": msg})

    def warn(self, msg: str) -> None:
        self.messages.append(msg)
        self.logs.put_nowait({"kind": "warn", "message": msg})

    def error(self, msg: str) -> None:
        self.ok = False
        self.messages.append(msg)
        self.logs.put_nowait({"kind": "error", "message": msg})


async def _forward_logs(logs: asyncio.Queue, broadcast: Broadcast) -> None:
    """Uno por fase; ``_run_unit`` lo drena (sentinel ``None``) antes del
    ``phase_status`` final, así ningún ``phase_log`` llega fuera de orden."""
    while (entry := await logs.get()) is not None:
        await broadcast(MessageType.PHASE_LOG, entry)


async def _run_unit(unit: Unit, broadcast: Broadcast, host: Host) -> UnitOutcome:
    collected = _Collected()
    for spec in unit.phases:
        await broadcast(MessageType.PHASE_STATUS, {"label": spec.label, "status": "running"})
        forwarder = asyncio.create_task(_forward_logs(collected.logs, broadcast))
        status = "done"
        try:
            await spec.run(collected, host)
        except PhaseError:
            status = "error"
        except Exception as exc:  # noqa: BLE001 — una fase con un bug no tumba el executor, se reporta como error
            collected.error(f"error inesperado: {exc}")
            status = "error"
        except BaseException:
            # Cancelación (o salida del proceso): no es un fallo de la fase,
            # sube tal cual — sin dejar el forwarder colgado.
            forwarder.cancel()
            raise
        collected.logs.put_nowait(None)
        await forwarder
        await broadcast(MessageType.PHASE_STATUS, {"label": spec.label, "status": status})
        if status == "error":
            break
    return UnitOutcome(
        service=unit.service,
        ok=collected.ok,
        message=" — ".join(collected.messages) or "sin mensaje",
    )


async def execute(plan: Plan, broadcast: Broadcast, host: Host) -> list[UnitOutcome]:
    results = []
    for batch in plan.batches:
        if batch.marker is not None:
            await broadcast(MessageType.PHASE_BATCH, {"batch": batch.marker})
        for unit in batch.units:
            outcome = await _run_unit(unit, broadcast, host)
            results.append(outcome)
            if not outcome.ok and plan.on_failure == "stop":
                return results
    return results


def bound_to(host: Host) -> Execute:
    """``execute`` sobre ``host``: lo que la composición le da a quien corre
    planes (``Lifecycle``) sin que conozca el host."""

    async def run(plan: Plan, broadcast: Broadcast) -> list[UnitOutcome]:
        return await execute(plan, broadcast, host)

    return run
