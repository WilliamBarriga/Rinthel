"""Las muestras de cada Telemetry stream, como valores inmutables. Sus campos
son el ``data`` del sobre: ``rinthel-client/src/protocol.rs`` los espeja y
``tests/protocol_fixtures/`` los ata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


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


# ``ready``: answers now; ``down``: should run but does not answer; ``off``:
# nothing to run (service disabled, or no usable Local model).
ServiceState = Literal["ready", "down", "off"]


@dataclass(frozen=True)
class CapabilityStatus:
    """One Capability: its active Local model id (``None`` when none is
    active), the state of the managed service that serves it and, when the
    active id cannot run, why (unknown id, GGUF not found)."""

    capability: str
    model: str | None
    state: ServiceState
    error: str | None = None


@dataclass(frozen=True)
class ServiceStatus:
    """A managed service that does not serve a Capability (Understory, Deck)."""

    name: str
    state: ServiceState


@dataclass(frozen=True)
class ModelsStatus:
    """What the Instance runs on its Platform: a service it does not run
    (disabled, voice without an active model, Linux-only on Windows) is
    simply not listed."""

    capabilities: list[CapabilityStatus]
    services: list[ServiceStatus]
