"""Las fuentes de telemetría en memoria: las usan los tests del Monitor y de
``/ws/monitor``, y pasan las mismas suites de contrato que las reales."""

from __future__ import annotations

from collections.abc import AsyncIterator

from rinthel_tui.clock import Clock, SystemClock
from rinthel_tui.monitoring.domain.types import (
    CapabilityStatus,
    CpuRamSample,
    DockerContainer,
    GpuSample,
    ModelsStatus,
)


class InMemoryGpu:
    """``sample`` es lo que reporta la GPU; ``None``, que no hay GPU."""

    def __init__(self, sample: GpuSample | None = None) -> None:
        self.sample = sample

    async def read(self) -> GpuSample:
        return self.sample or GpuSample(available=False)


class InMemoryHost:
    def __init__(self, sample: CpuRamSample = CpuRamSample(17.3, 12.4, 64.0, 19.4)) -> None:
        self.sample = sample

    async def read(self) -> CpuRamSample:
        return self.sample


class InMemoryContainers:
    """``running`` son los contenedores de los proyectos compose, arriba o
    no."""

    def __init__(self, running: list[DockerContainer] | None = None) -> None:
        self.running = list(running or [])

    async def containers(self) -> list[DockerContainer]:
        return list(self.running)


class InMemoryLog:
    """``write`` agrega líneas; ``missing = True`` es un log que todavía no
    existe (el primer ``write`` lo crea). ``follow`` manda las últimas
    ``backlog`` y después las nuevas."""

    def __init__(self, *, backlog: int = 50, poll: float = 0.001, clock: Clock | None = None) -> None:
        self.lines: list[str] = []
        self.missing = False
        self._backlog = backlog
        self._poll = poll
        self._clock = clock or SystemClock()

    def write(self, *lines: str) -> None:
        self.missing = False
        self.lines += lines

    async def follow(self) -> AsyncIterator[str]:
        pos = max(0, len(self.lines) - self._backlog)
        if self.missing:
            yield "[daemon] esperando el log en memoria"
            while self.missing:
                await self._clock.sleep(self._poll)
            pos = 0
        while True:
            while pos < len(self.lines):
                yield self.lines[pos]
                pos += 1
            await self._clock.sleep(self._poll)


class InMemoryModels:
    """``status`` is what the Instance reports; the test changes it."""

    def __init__(self, status: ModelsStatus | None = None) -> None:
        self.status = status or ModelsStatus(capabilities=[CapabilityStatus("llm", None, "off")], services=[])

    async def read(self) -> ModelsStatus:
        return self.status
