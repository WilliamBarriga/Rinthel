"""La composición de lifecycle (ADR 0004): arma el ``Host`` con el adapter real
de cada puerto. Lo llaman los puntos de entrada — ``Adapters.from_cfg`` — y
nadie más elige un adapter."""

from rinthel_tui.clock import SystemClock
from rinthel_tui.lifecycle.adapters.asyncio_processes import AsyncioProcesses
from rinthel_tui.lifecycle.adapters.asyncio_runner import AsyncioRunner
from rinthel_tui.lifecycle.adapters.data_dirs import SystemDataDirs
from rinthel_tui.lifecycle.adapters.docker_compose import DockerCompose
from rinthel_tui.lifecycle.adapters.host_info import SystemHostInfo
from rinthel_tui.lifecycle.adapters.npm_registry import NpmRegistry
from rinthel_tui.lifecycle.adapters.socket_probe import SocketProbe
from rinthel_tui.lifecycle.domain.host import Host


def real_host() -> Host:
    runner = AsyncioRunner()
    return Host(
        runner=runner,
        processes=AsyncioProcesses(),
        compose=DockerCompose(runner),
        probe=SocketProbe(),
        clock=SystemClock(),
        host_info=SystemHostInfo(),
        registry=NpmRegistry(),
        data_dirs=SystemDataDirs(),
    )
