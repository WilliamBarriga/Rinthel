"""El Monitor: dueño de la lista de Telemetry streams. ``stream()`` arranca,
por cliente, una tarea por source de la lista y mezcla lo que producen en
un único flujo de sobres ``{type, data}`` — el handler de ``/ws/monitor``
solo lo bombea hacia el cliente. Una source que levanta se loguea y se
reinicia a los ``restart_delay`` segundos: el flujo mezclado nunca muere por
una sola source."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import asdict, dataclass

from rinthel_tui.clock import Clock
from rinthel_tui.monitoring.domain.envelope import MessageType, envelope
from rinthel_tui.monitoring.domain.ports import ContainerStatus, GpuSensor, HostSensor, ServiceLog, ServiceReadiness

log = logging.getLogger(__name__)

Source = Callable[[], AsyncIterator[dict]]


@dataclass(frozen=True)
class Stream:
    type: MessageType
    source: Source


@dataclass(frozen=True)
class TelemetrySources:
    """Un adapter por puerto de telemetría. ``create_app`` arma los reales;
    los tests, los en memoria."""

    gpu: GpuSensor
    host: HostSensor
    containers: ContainerStatus
    log: ServiceLog
    llama: ServiceReadiness


def every(interval: float, sample: Callable[[], Awaitable[dict]], *, clock: Clock) -> Source:
    """Source periódica: una muestra ya y después una cada ``interval``
    segundos del ``clock``. Una muestra que levanta se loguea y se saltea."""
    async def source() -> AsyncIterator[dict]:
        while True:
            try:
                yield await sample()
            except Exception:
                log.exception("muestra de %s falló", getattr(sample, "__name__", sample))
            await clock.sleep(interval)

    return source


class Monitor:
    def __init__(
        self, streams: Sequence[Stream], *, restart_delay: float = 1.0, buffer: int = 64, clock: Clock
    ) -> None:
        self.streams = streams
        self.restart_delay = restart_delay
        self.buffer = buffer
        self.clock = clock

    async def stream(self) -> AsyncIterator[str]:
        # Acotada: un cliente lento frena a las sources en vez de acumular
        # mensajes en memoria.
        out: asyncio.Queue[str] = asyncio.Queue(maxsize=self.buffer)

        async def pump(stream: Stream) -> None:
            while True:
                try:
                    async for data in stream.source():
                        await out.put(envelope(stream.type, data))
                except Exception:
                    log.exception("source %s falló; se reinicia", stream.type)
                await self.clock.sleep(self.restart_delay)

        tasks = [asyncio.create_task(pump(s)) for s in self.streams]
        try:
            while True:
                yield await out.get()
        finally:
            for t in tasks:
                t.cancel()
            # Esperarlas: una source cancelada puede tener limpieza pendiente
            # (matar un subproceso) que se pierde si el loop cierra antes.
            await asyncio.gather(*tasks, return_exceptions=True)


def streams(sources: TelemetrySources, *, clock: Clock) -> list[Stream]:
    """La lista de Telemetry streams: qué fuente alimenta cada ``type`` y
    cada cuánto se muestrea. ``clock`` marca el ritmo de las muestras
    periódicas. ``llama_status`` es un estado parado, no un evento: si
    llama-server responde ahora."""

    async def gpu_sample() -> dict:
        return asdict(await sources.gpu.read())

    async def cpu_ram_sample() -> dict:
        return asdict(await sources.host.read())

    async def docker_status() -> dict:
        return {"containers": [asdict(c) for c in await sources.containers.containers()]}

    async def log_line() -> AsyncIterator[dict]:
        async for line in sources.log.follow():
            yield {"line": line}

    async def llama_status() -> dict:
        return {"ready": await sources.llama.ready()}

    return [
        Stream(MessageType.DOCKER_STATUS, every(3.0, docker_status, clock=clock)),
        Stream(MessageType.GPU_SAMPLE, every(1.5, gpu_sample, clock=clock)),
        Stream(MessageType.CPU_RAM_SAMPLE, every(1.5, cpu_ram_sample, clock=clock)),
        Stream(MessageType.LOG_LINE, log_line),
        Stream(MessageType.LLAMA_STATUS, every(2.0, llama_status, clock=clock)),
    ]
