"""Las muestras de cada Telemetry stream, como valores inmutables. Sus campos
son el ``data`` del sobre: ``rinthel-client/src/protocol.rs`` los espeja y
``tests/protocol_fixtures/`` los ata."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GpuSample:
    """``available=False`` sin GPU NVIDIA o sin poder leerla; un campo que la
    GPU no reporta es ``None``."""

    available: bool
    utilization: float | None = None  # %
    memory_used: float | None = None  # MiB
    memory_total: float | None = None  # MiB
    temperature: float | None = None  # °C
    power_draw: float | None = None  # W


@dataclass(frozen=True)
class CpuRamSample:
    cpu_percent: float
    ram_used_gb: float
    ram_total_gb: float
    ram_percent: float


@dataclass(frozen=True)
class DockerContainer:
    name: str
    state: str
    ports: str
    status: str
