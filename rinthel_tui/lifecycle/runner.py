"""Corre una lista declarativa de PhaseSpec en secuencia.

Quien llama a ``run_phase_list`` decide qué hacer con cada llamada a
``report``. Si una fase levanta PhaseError la secuencia se corta ahí, porque
las fases siguientes suelen depender de que la anterior haya funcionado
(ej. no tiene sentido esperar a que llama-server responda si nunca se lo
pudo lanzar).
"""

import inspect
from typing import Awaitable, Callable, Sequence, Union

from rinthel_tui.config import RinthelConfig
from rinthel_tui.lifecycle.specs import PhaseSpec
from rinthel_tui.lifecycle.types import PhaseError, PhaseReport

# status: "running" | "done" | "error" — avisa a quien llama antes/después de
# cada fase para que pueda reflejarlo en un checklist. Puede devolver un
# awaitable (el daemon lo usa para transmitir por /ws/monitor) o nada — se
# espera el resultado solo si hace falta, así los dos casos conviven sin
# wrapper.
PhaseCallback = Callable[[PhaseSpec, str], Union[Awaitable[None], None]]


class PhaseFailed(Exception):
    """La secuencia se detuvo: una fase de la lista falló."""

    def __init__(self, label: str, cause: Exception):
        super().__init__(f"{label}: {cause}")
        self.label = label
        self.cause = cause


async def _notify(on_phase: PhaseCallback, spec: PhaseSpec, status: str) -> None:
    result = on_phase(spec, status)
    if inspect.isawaitable(result):
        await result


async def run_phase_list(
    cfg: RinthelConfig,
    specs: Sequence[PhaseSpec],
    report: PhaseReport,
    on_phase: PhaseCallback | None = None,
) -> None:
    for spec in specs:
        if on_phase:
            await _notify(on_phase, spec, "running")
        try:
            await spec.run(cfg, report)
        except PhaseError as exc:
            if on_phase:
                await _notify(on_phase, spec, "error")
            raise PhaseFailed(spec.label, exc) from exc
        if on_phase:
            await _notify(on_phase, spec, "done")
