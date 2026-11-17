"""Suite de contrato del puerto ``Processes``: procesos reales (asyncio y
señales) y ``FakeProcesses`` pasan lo mismo. Esperar a que algo pare usa el
reloj real, que con el fake no espera nada."""

import asyncio
import socket
import sys
from dataclasses import dataclass

import pytest

from rinthel_tui.lifecycle.adapters.asyncio_processes import AsyncioProcesses
from rinthel_tui.lifecycle.adapters.windows_processes import WindowsProcesses
from rinthel_tui.lifecycle.domain.errors import SpawnFailed
from rinthel_tui.lifecycle.domain.types import ProcessHandle
from tests.lifecycle.fakes import FakeProcesses

SLEEPS = ["sleep", "30"]
STUBBORN = ["sh", "-c", "trap '' TERM; sleep 30"]
EXITS = ["sh", "-c", "exit 1"]


class _Tracking(AsyncioProcesses):
    """El adapter real, anotando los pids para no dejar procesos al terminar el test."""

    def __init__(self) -> None:
        super().__init__()
        self.handles: list[ProcessHandle] = []

    async def spawn(self, *args, **kwargs) -> ProcessHandle:
        handle = await super().spawn(*args, **kwargs)
        self.handles.append(handle)
        return handle


class _TrackingWindows(WindowsProcesses):
    """El adapter Windows con ``creationflags=0``: en Linux el flag de Windows no existe."""

    def __init__(self) -> None:
        super().__init__(creationflags=0)
        self.handles: list[ProcessHandle] = []

    async def spawn(self, *args, **kwargs) -> ProcessHandle:
        handle = await super().spawn(*args, **kwargs)
        self.handles.append(handle)
        return handle


@dataclass
class World:
    processes: object
    script: object  # (argv, **behaviour) -> None: solo el fake necesita el guion
    serve: object  # async (port, *, ignore_term) -> ProcessHandle: un proceso escuchando en ``port``


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _listener_argv(port: int, *, ignore_term: bool) -> list[str]:
    trap = "import signal; signal.signal(signal.SIGTERM, signal.SIG_IGN); " if ignore_term else ""
    return [
        sys.executable, "-c",
        f"{trap}import socket, time; s = socket.socket(); s.bind(('127.0.0.1', {port})); s.listen(); time.sleep(30)",
    ]


def _port_open(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


@pytest.fixture(params=["asyncio", "windows", "fake"])
async def world(request, tmp_path):
    if request.param == "fake":
        fake = FakeProcesses()

        async def fake_serve(port: int, *, ignore_term: bool = False) -> ProcessHandle:
            argv = _listener_argv(port, ignore_term=ignore_term)
            fake.script(argv, ignore_term=ignore_term)
            handle = await fake.spawn(argv, log=tmp_path / "listener.log")
            fake.listen(port, handle)
            return handle

        yield World(fake, fake.script, fake_serve)
        return
    real = _Tracking() if request.param == "asyncio" else _TrackingWindows()

    async def real_serve(port: int, *, ignore_term: bool = False) -> ProcessHandle:
        handle = await real.spawn(_listener_argv(port, ignore_term=ignore_term), log=tmp_path / "listener.log")
        assert await _until(lambda: _port_open(port))
        return handle

    yield World(real, lambda argv, **behaviour: None, real_serve)
    for handle in real.handles:
        real.kill(handle)


# Las esperas son del reloj real a propósito: el adapter real manda señales a
# procesos reales, y un ``ManualClock`` no los hace avanzar. Con el fake no esperan.
async def _until(predicate, timeout: float = 5.0) -> bool:
    waited = 0.0
    while not predicate():
        if waited >= timeout:
            return False
        await asyncio.sleep(0.02)  # espera real: es un proceso del SO, sin reloj que inyectar
        waited += 0.02
    return True


async def test_a_spawned_process_is_alive(world, tmp_path):
    handle = await world.processes.spawn(SLEEPS, log=tmp_path / "p.log")

    assert world.processes.is_alive(handle)


async def test_terminate_stops_a_process(world, tmp_path):
    handle = await world.processes.spawn(SLEEPS, log=tmp_path / "p.log")

    world.processes.terminate(handle)

    assert await _until(lambda: not world.processes.is_alive(handle))


async def test_a_process_that_ignores_terminate_dies_on_kill(world, tmp_path):
    world.script(STUBBORN, ignore_term=True)
    handle = await world.processes.spawn(STUBBORN, log=tmp_path / "p.log")
    await asyncio.sleep(0.2)  # que el shell alcance a instalar el trap

    world.processes.terminate(handle)
    await asyncio.sleep(0.2)  # que el TERM ignorado tenga tiempo de matarlo si no lo ignorara
    assert world.processes.is_alive(handle)

    world.processes.kill(handle)
    assert await _until(lambda: not world.processes.is_alive(handle))


async def test_a_process_that_exits_on_its_own_is_not_alive(world, tmp_path):
    world.script(EXITS, exits=True)
    handle = await world.processes.spawn(EXITS, log=tmp_path / "p.log")

    assert await _until(lambda: not world.processes.is_alive(handle))


async def test_terminating_or_killing_a_dead_process_does_nothing(world, tmp_path):
    handle = await world.processes.spawn(SLEEPS, log=tmp_path / "p.log")
    world.processes.kill(handle)
    assert await _until(lambda: not world.processes.is_alive(handle))

    world.processes.terminate(handle)
    world.processes.kill(handle)

    assert not world.processes.is_alive(handle)


async def test_a_command_that_cannot_start_raises_spawn_failed(world, tmp_path):
    missing = ["rinthel-no-such-binary-xyz"]
    world.script(missing, missing=True)

    with pytest.raises(SpawnFailed):
        await world.processes.spawn(missing, log=tmp_path / "p.log")


async def test_stop_listeners_with_nobody_listening_signals_nobody(world):
    assert await world.processes.stop_listeners(_free_port()) == []


async def test_stop_listeners_stops_whoever_listens_on_the_port(world):
    port = _free_port()
    handle = await world.serve(port)

    assert await world.processes.stop_listeners(port) == [handle.pid]
    assert await _until(lambda: not world.processes.is_alive(handle))


async def test_a_listener_that_ignores_terminate_only_stops_when_forced(world):
    port = _free_port()
    handle = await world.serve(port, ignore_term=True)

    await world.processes.stop_listeners(port)
    await asyncio.sleep(0.2)  # que el TERM ignorado tenga tiempo de matarlo si no lo ignorara
    assert world.processes.is_alive(handle)

    assert await world.processes.stop_listeners(port, force=True) == [handle.pid]
    assert await _until(lambda: not world.processes.is_alive(handle))
