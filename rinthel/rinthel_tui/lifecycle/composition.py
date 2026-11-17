"""La composición de lifecycle (ADR 0004): arma el ``Host`` con el adapter real
de cada puerto. Lo llaman los puntos de entrada — ``Adapters.from_cfg`` — y
nadie más elige un adapter."""

import os

from rinthel_tui.clock import SystemClock
from rinthel_tui.lifecycle.adapters.asyncio_processes import AsyncioProcesses
from rinthel_tui.lifecycle.adapters.asyncio_runner import AsyncioRunner
from rinthel_tui.lifecycle.adapters.data_dirs import SystemDataDirs
from rinthel_tui.lifecycle.adapters.docker_compose import DockerCompose
from rinthel_tui.lifecycle.adapters.host_info import SystemHostInfo
from rinthel_tui.lifecycle.adapters.npm_registry import NpmRegistry
from rinthel_tui.lifecycle.adapters.socket_probe import SocketProbe
from rinthel_tui.lifecycle.adapters.windows_host_info import WindowsHostInfo
from rinthel_tui.lifecycle.adapters.windows_processes import WindowsProcesses, WindowsRunner
from rinthel_tui.lifecycle.domain.host import Host


def real_host(os_name: str = os.name) -> Host:
    """The only place that looks at the operating system: ``nt`` gets the
    Windows adapters of the runner, processes and host info. The rest
    (``SocketProbe``, docker compose, data dirs) is the same on both."""
    windows = os_name == "nt"
    runner = WindowsRunner() if windows else AsyncioRunner()
    return Host(
        runner=runner,
        processes=WindowsProcesses() if windows else AsyncioProcesses(),
        compose=DockerCompose(runner),
        probe=SocketProbe(),
        clock=SystemClock(),
        host_info=WindowsHostInfo() if windows else SystemHostInfo(),
        registry=NpmRegistry(),
        data_dirs=SystemDataDirs(),
    )
