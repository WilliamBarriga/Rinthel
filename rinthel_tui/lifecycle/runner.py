"""Corre una lista declarativa de PhaseSpec en secuencia.

Reemplaza ``nightcity/framework/rinthel-phase-runner.sh`` (``nc_run_phase_list``).
A diferencia del bash, no hay distinción TUI/texto-plano: quien llama a
``run_phase_list`` (una Screen de Textual, o el script de prueba suelto)
decide qué hacer con cada llamada a ``report``. Si una fase levanta
PhaseError la secuencia se corta ahí — igual que el ``set -e``/``exit 1``
del script bash corriendo en directo, porque las fases siguientes suelen
depender de que la anterior haya funcionado (ej. no tiene sentido esperar
a que llama-server responda si nunca se lo pudo lanzar).
"""

from typing import Sequence

from rinthel_tui.config import RinthelConfig
from rinthel_tui.lifecycle.phases import PhaseError, PhaseReport
from rinthel_tui.lifecycle.specs import PhaseSpec


class PhaseFailed(Exception):
    """La secuencia se detuvo: una fase de la lista falló."""

    def __init__(self, label: str, cause: Exception):
        super().__init__(f"{label}: {cause}")
        self.label = label
        self.cause = cause


async def run_phase_list(cfg: RinthelConfig, specs: Sequence[PhaseSpec], report: PhaseReport) -> None:
    for spec in specs:
        try:
            await spec.run(cfg, report)
        except PhaseError as exc:
            raise PhaseFailed(spec.label, exc) from exc
