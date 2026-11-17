"""La composición de lifecycle elige el adapter real de cada puerto (ADR 0004):
es el único lugar, junto a los puntos de entrada que la llaman."""

import dataclasses

from rinthel_tui.clock import SystemClock
from rinthel_tui.lifecycle.adapters.asyncio_processes import AsyncioProcesses
from rinthel_tui.lifecycle.adapters.asyncio_runner import AsyncioRunner
from rinthel_tui.lifecycle.adapters.data_dirs import SystemDataDirs
from rinthel_tui.lifecycle.adapters.docker_compose import DockerCompose
from rinthel_tui.lifecycle.adapters.host_info import SystemHostInfo
from rinthel_tui.lifecycle.adapters.npm_registry import NpmRegistry
from rinthel_tui.lifecycle.adapters.socket_probe import SocketProbe
from rinthel_tui.lifecycle.composition import real_host


def test_the_real_host_has_a_real_adapter_per_port():
    host = real_host()

    assert isinstance(host.runner, AsyncioRunner)
    assert isinstance(host.processes, AsyncioProcesses)
    assert isinstance(host.compose, DockerCompose)
    assert isinstance(host.probe, SocketProbe)
    assert isinstance(host.clock, SystemClock)
    assert isinstance(host.host_info, SystemHostInfo)
    assert isinstance(host.registry, NpmRegistry)
    assert isinstance(host.data_dirs, SystemDataDirs)


def test_the_host_has_exactly_the_eight_ports():
    assert [f.name for f in dataclasses.fields(real_host())] == [
        "runner", "processes", "compose", "probe", "clock", "host_info", "registry", "data_dirs",
    ]
