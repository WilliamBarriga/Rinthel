"""Suite de contrato de ``ServiceLog``: corre igual contra el ``llama.log``
de la Instance del test (``tail`` sobre el filesystem) y el en memoria."""

import asyncio
import dataclasses

import pytest

from rinthel_tui.clock import ManualClock
from rinthel_tui.monitoring.adapters.log_file import FileLog
from rinthel_tui.monitoring.adapters.memory import InMemoryLog


class FileHarness:
    def __init__(self, cfg, tmp_path, clock) -> None:
        self.path = tmp_path / "llama.log"
        cfg = dataclasses.replace(cfg, llama=dataclasses.replace(cfg.llama, log=self.path))
        self.log = FileLog(lambda: cfg, poll=0.01, clock=clock)

    def write(self, *lines: str) -> None:
        with self.path.open("a") as f:
            f.writelines(line + "\n" for line in lines)


class MemoryHarness:
    def __init__(self, cfg, tmp_path, clock) -> None:
        self.log = InMemoryLog(clock=clock)
        self.log.missing = True

    def write(self, *lines: str) -> None:
        self.log.write(*lines)


@pytest.fixture
def clock() -> ManualClock:
    return ManualClock()


@pytest.fixture(params=[FileHarness, MemoryHarness], ids=["file", "memory"])
def harness(request, cfg, tmp_path, clock):
    return request.param(cfg, tmp_path, clock)


async def polls(clock: ManualClock, n: int) -> None:
    """Deja que la fuente mire su log ``n`` veces más: espera los ``sleep``
    del reloj, no tiempo."""
    target = len(clock.sleeps) + n
    while len(clock.sleeps) < target:
        await asyncio.sleep(0)


async def take(source, n: int) -> list[str]:
    return [await asyncio.wait_for(anext(source), timeout=1) for _ in range(n)]


async def test_sends_the_lines_already_there_then_the_new_ones_in_order(harness):
    harness.write("uno", "dos")
    source = harness.log.follow()

    assert await take(source, 2) == ["uno", "dos"]
    harness.write("tres", "cuatro")
    assert await take(source, 2) == ["tres", "cuatro"]


async def test_without_a_log_it_sends_one_waiting_line_then_the_log_once_it_appears(harness, clock):
    source = harness.log.follow()

    [waiting] = await take(source, 1)
    assert waiting.startswith("[daemon] esperando ")
    pending = asyncio.ensure_future(anext(source))
    await polls(clock, 5)
    assert not pending.done()  # una sola línea de espera

    harness.write("arrancó")
    assert await asyncio.wait_for(pending, timeout=1) == "arrancó"
