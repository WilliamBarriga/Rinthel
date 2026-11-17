"""Un puerto por fuente de telemetría: los define el dominio, del lado del
Monitor que los muestrea. Cada uno tiene un adapter real y uno en memoria, y
una suite de contrato que corre contra los dos
(``tests/monitoring/test_*_contract.py``). Ninguno levanta: una fuente que
no puede leer lo dice en su muestra. El ``cfg`` vivo, si lo necesitan, lo lee
el adapter por su cuenta."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from rinthel_tui.monitoring.domain.types import CpuRamSample, DockerContainer, GpuSample


class GpuSensor(Protocol):
    async def read(self) -> GpuSample:
        """La GPU ahora; ``GpuSample(available=False)`` si no hay o no se
        puede leer."""
        ...


class HostSensor(Protocol):
    async def read(self) -> CpuRamSample:
        """CPU y RAM del host ahora."""
        ...


class ContainerStatus(Protocol):
    async def containers(self) -> list[DockerContainer]:
        """Los contenedores de los proyectos compose de la Instance, arriba o
        no; ``[]`` si no hay Docker o ningún proyecto."""
        ...


class ServiceLog(Protocol):
    def follow(self) -> AsyncIterator[str]:
        """``tail -f`` del log de llama-server: las últimas líneas y después
        las que se agregan, completas y en orden. Sin log todavía, una línea
        de espera y sigue esperando. No termina; cancelarlo lo cierra."""
        ...


class ServiceReadiness(Protocol):
    async def ready(self) -> bool:
        """Si el servicio responde ahora en su URL de readiness: un solo
        intento, sin esperar. En llama-server esa URL queda detrás de un único
        gate que solo se levanta con el modelo cargado, así que ``True`` ya
        implica servidor arriba y modelo cargado."""
        ...
