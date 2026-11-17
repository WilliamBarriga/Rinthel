"""``Monitor(streams).stream()``: un flujo de sobres ``{type, data}`` por
cliente, mezclando todas las sources de la lista. Sources falsas, o la
lista sobre las fuentes en memoria."""

import asyncio
import json

from rinthel_tui.clock import ManualClock
from rinthel_tui.monitoring.adapters.memory import (
    InMemoryContainers,
    InMemoryGpu,
    InMemoryHost,
    InMemoryLog,
    InMemoryReadiness,
)
from rinthel_tui.monitoring.domain.envelope import MessageType
from rinthel_tui.monitoring.domain.monitor import (
    Monitor,
    Stream,
    TelemetrySources,
    every,
    streams,
)
from rinthel_tui.monitoring.domain.types import CpuRamSample, DockerContainer, GpuSample


def once(*samples: dict):
    async def source():
        for sample in samples:
            yield sample
        await asyncio.Event().wait()  # una source real no termina

    return source


def memory_sources() -> TelemetrySources:
    return TelemetrySources(
        gpu=InMemoryGpu(), host=InMemoryHost(), containers=InMemoryContainers(), log=InMemoryLog(),
        llama=InMemoryReadiness(),
    )


async def take(monitor: Monitor, n: int) -> list[dict]:
    stream = monitor.stream()
    try:
        return [json.loads(await anext(stream)) for _ in range(n)]
    finally:
        await stream.aclose()


async def test_every_stream_arrives_in_its_own_envelope():
    monitor = Monitor([
        Stream(MessageType.GPU_SAMPLE, once({"util": 40})),
        Stream(MessageType.LOG_LINE, once({"line": "a"}, {"line": "b"})),
    ], clock=ManualClock())

    messages = await asyncio.wait_for(take(monitor, 3), timeout=1)

    assert sorted(messages, key=json.dumps) == sorted([
        {"type": "gpu_sample", "data": {"util": 40}},
        {"type": "log_line", "data": {"line": "a"}},
        {"type": "log_line", "data": {"line": "b"}},
    ], key=json.dumps)


async def test_a_failing_source_restarts_without_cutting_the_others():
    clock = ManualClock()
    starts = 0

    async def flaky():
        nonlocal starts
        starts += 1
        if starts == 1:
            raise OSError("se cayó")
        yield {"line": f"arranque n{starts}"}
        await asyncio.Event().wait()

    monitor = Monitor(
        [Stream(MessageType.LOG_LINE, flaky), Stream(MessageType.GPU_SAMPLE, once({"util": 1}))],
        clock=clock,
    )

    messages = await asyncio.wait_for(take(monitor, 2), timeout=1)

    assert {"type": "gpu_sample", "data": {"util": 1}} in messages
    assert {"type": "log_line", "data": {"line": "arranque n2"}} in messages
    assert clock.sleeps == [1.0]  # esperó su restart_delay en el reloj, no en tiempo real


async def test_a_periodic_source_samples_now_and_then_once_per_interval_of_the_clock():
    clock = ManualClock()
    n = 0

    async def sample() -> dict:
        nonlocal n
        n += 1
        return {"n": n}

    source = every(1.5, sample, clock=clock)()

    assert [await anext(source) for _ in range(3)] == [{"n": 1}, {"n": 2}, {"n": 3}]
    assert clock.sleeps == [1.5, 1.5]
    await source.aclose()


def test_streams_has_the_five_telemetry_streams():
    assert sorted(s.type.value for s in streams(memory_sources(), clock=ManualClock())) == [
        "cpu_ram_sample",
        "docker_status",
        "gpu_sample",
        "llama_status",
        "log_line",
    ]


async def test_the_llama_stream_says_whether_llama_server_answers_now():
    sources = memory_sources()
    sources.llama.is_ready = True
    clock = ManualClock()
    monitor = Monitor([s for s in streams(sources, clock=clock) if s.type is MessageType.LLAMA_STATUS], clock=clock)

    [message] = await asyncio.wait_for(take(monitor, 1), timeout=1)

    assert message == {"type": "llama_status", "data": {"ready": True}}


async def test_a_client_that_stops_reading_holds_the_sources_back():
    produced = 0

    async def firehose():
        nonlocal produced
        while True:
            produced += 1
            yield {"line": str(produced)}
            await asyncio.sleep(0)

    stream = Monitor([Stream(MessageType.LOG_LINE, firehose)], buffer=4, clock=ManualClock()).stream()
    try:
        await anext(stream)
        for _ in range(50):  # el cliente no lee más: el loop corre hasta quedar quieto
            await asyncio.sleep(0)
        assert produced <= 4 + 2
    finally:
        await stream.aclose()


async def test_closing_the_stream_waits_for_the_sources_to_clean_up():
    cleaned = False

    async def slow_to_stop():
        nonlocal cleaned
        try:
            yield {"line": "a"}
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0)  # como matar y esperar un subproceso
            cleaned = True

    monitor = Monitor([Stream(MessageType.LOG_LINE, slow_to_stop)], clock=ManualClock())

    await asyncio.wait_for(take(monitor, 1), timeout=1)

    assert cleaned


async def test_each_stream_carries_the_reading_of_its_source():
    sources = memory_sources()
    sources.gpu.sample = GpuSample(True, 42.0, 8192.0, 24576.0, 61.0, 210.5)
    sources.host.sample = CpuRamSample(17.3, 12.4, 64.0, 19.4)
    sources.containers.running = [DockerContainer("understory-1", "running", "3800->3800", "Up 1m")]
    sources.log.write("srv listo")
    clock = ManualClock()
    monitor = Monitor([s for s in streams(sources, clock=clock) if s.type is not MessageType.LLAMA_STATUS], clock=clock)

    messages = {m["type"]: m["data"] for m in await asyncio.wait_for(take(monitor, 4), timeout=1)}

    assert messages == {
        "gpu_sample": {
            "available": True, "utilization": 42.0, "memory_used": 8192.0,
            "memory_total": 24576.0, "temperature": 61.0, "power_draw": 210.5,
        },
        "cpu_ram_sample": {"cpu_percent": 17.3, "ram_used_gb": 12.4, "ram_total_gb": 64.0, "ram_percent": 19.4},
        "docker_status": {"containers": [
            {"name": "understory-1", "state": "running", "ports": "3800->3800", "status": "Up 1m"},
        ]},
        "log_line": {"line": "srv listo"},
    }
