"""The lifecycle composition (ports-and-adapters ADR): builds the ``Host``
with the real adapter of each port. The entry points call it
(``Adapters.from_cfg``, the daemon and CLI ``main``s) and nobody else picks
an adapter."""

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
from rinthel_tui.lifecycle.domain.ports import HostInfo


def real_host_info(os_name: str = os.name) -> HostInfo:
    """The ``HostInfo`` of this machine: what ``default_config`` takes its
    Platform from."""
    return WindowsHostInfo() if os_name == "nt" else SystemHostInfo()


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
        host_info=real_host_info(os_name),
        registry=NpmRegistry(),
        data_dirs=SystemDataDirs(),
    )
