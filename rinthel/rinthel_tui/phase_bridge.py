"""Adapta ``PhaseReport`` a los ``ServiceOutcome`` de ``daemon.py`` (POST
/boot, /terminate, /reload, /install) y a la telemetría de fase de
``/ws/monitor`` — ver docs/adr/0001 y el docstring de ``daemon.py``.

Recibe ``broadcast`` por parámetro en vez de importarlo de ``daemon.py``:
evita un ciclo de imports (``daemon`` ya importa este módulo) y permite
testear ``run_unit`` sin un WebSocket real ni monkeypatchear nada — se le
pasa una función de prueba directo.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from rinthel_tui.config import RinthelConfig
from rinthel_tui.lifecycle.runner import PhaseCallback, PhaseFailed, run_phase_list
from rinthel_tui.lifecycle.specs import PhaseSpec

Broadcast = Callable[[str, dict], Awaitable[None]]


@dataclass
class _Collected:
    """``PhaseReport`` que junta los mensajes terminales (success/warn/error)
    de una unidad de servicio en un solo ``ServiceOutcome`` — ver
    docs/adr/0001. ``info()`` se descarta a propósito: es ruido de proceso
    (stdout de ``docker compose``, hints supletorios como el de
    ``on_timeout_hint``), no el resultado en sí; cada fase de
    ``managed_service.py`` siempre termina con un success/warn/error real,
    así que no se pierde la señal que importa. Se concatena en vez de
    quedarse con el último mensaje: spawn y wait son eventos distintos y los
    dos aportan contexto."""

    ok: bool = True
    messages: list[str] = field(default_factory=list)

    def info(self, msg: str) -> None:
        pass

    def success(self, msg: str) -> None:
        self.messages.append(msg)

    def warn(self, msg: str) -> None:
        self.messages.append(msg)

    def error(self, msg: str) -> None:
        self.ok = False
        self.messages.append(msg)


@dataclass(kw_only=True)
class _BroadcastingCollected(_Collected):
    """``_Collected`` + un ``phase_log`` por ``/ws/monitor`` en cada llamada
    — a diferencia de ``_Collected.info()``, acá sí se transmite (es ruido
    para el ``message`` final del ``ServiceOutcome``, pero es justo lo que
    el cliente muestra en vivo). Broadcast es fire-and-forget
    (``asyncio.create_task``, no awaited): perder un mensaje de progreso
    (cliente desconectado a mitad de un boot) no afecta el
    ``ServiceOutcome`` final; las llamadas base siguen alimentando
    ``ok``/``messages`` sin cambios.

    ``kw_only=True`` en esta clase (no en ``_Collected``) para poder sumar
    ``broadcast`` sin default después de los campos con default de la
    base — mismo patrón que ``managed_service._ServiceBase``."""

    broadcast: Broadcast

    def info(self, msg: str) -> None:
        super().info(msg)
        asyncio.create_task(self.broadcast("phase_log", {"kind": "info", "message": msg}))

    def success(self, msg: str) -> None:
        super().success(msg)
        asyncio.create_task(self.broadcast("phase_log", {"kind": "success", "message": msg}))

    def warn(self, msg: str) -> None:
        super().warn(msg)
        asyncio.create_task(self.broadcast("phase_log", {"kind": "warn", "message": msg}))

    def error(self, msg: str) -> None:
        super().error(msg)
        asyncio.create_task(self.broadcast("phase_log", {"kind": "error", "message": msg}))


async def _run_phase_list_safe(
    cfg: RinthelConfig,
    unit_specs: list[PhaseSpec],
    collected: _Collected,
    on_phase: PhaseCallback,
) -> None:
    """Corre ``run_phase_list`` absorbiendo cualquier excepción en un
    resultado de ``collected`` en vez de dejarla subir. ``PhaseFailed`` ya
    marca ``collected.ok = False`` vía ``report.error()`` (fallo esperado,
    ya reportado por la fase que lo levantó); cualquier otra excepción (bug,
    IO real) no lo hace por su cuenta, así que acá se convierte a mano — es
    lo que le permite a ``/terminate`` seguir con la unidad siguiente aunque
    una explote con algo que no sea ``PhaseError``, en vez de abortar la
    secuencia entera (antes de esto, una excepción no prevista en una
    unidad de ``down_units`` mataba la list-comprehension completa de
    ``/terminate`` y ninguna unidad posterior llegaba a correr — justo lo
    contrario del "sigue con las que quedan aunque una falle" documentado
    en CONTEXT.md)."""
    try:
        await run_phase_list(cfg, unit_specs, collected, on_phase=on_phase)
    except PhaseFailed:
        pass
    except Exception as exc:
        collected.error(f"error inesperado: {exc}")


async def run_unit(
    cfg: RinthelConfig, service: str, unit_specs: list[PhaseSpec], broadcast: Broadcast
) -> dict:
    """Corre ``unit_specs`` (las fases de un servicio, ver
    ``lifecycle/specs.py::*_units``) y arma el ``{"service", "ok",
    "message"}`` que espera el cliente Rust, transmitiendo
    ``phase_status``/``phase_log`` por ``broadcast`` en el camino. Nunca
    levanta — ver ``_run_phase_list_safe``."""

    async def _on_phase(spec: PhaseSpec, status: str) -> None:
        await broadcast("phase_status", {"label": spec.label, "status": status})

    collected = _BroadcastingCollected(broadcast=broadcast)
    await _run_phase_list_safe(cfg, unit_specs, collected, _on_phase)
    return {
        "service": service,
        "ok": collected.ok,
        "message": " — ".join(collected.messages) or "sin mensaje",
    }
