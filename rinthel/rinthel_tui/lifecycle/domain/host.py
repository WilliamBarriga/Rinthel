"""``Host``: los ocho puertos de lifecycle juntos, la forma de composición
del dominio. Es el primer
argumento de toda phase: ``fn(host, report, **kwargs)``. Lo arma el punto de
entrada con los adapters reales y las pruebas con dobles."""

from dataclasses import dataclass

from rinthel_tui.clock import Clock
from rinthel_tui.lifecycle.domain.ports import (
    Compose,
    DataDirs,
    HostInfo,
    PackageRegistry,
    Probe,
    Processes,
    Runner,
)


@dataclass(frozen=True)
class Host:
    runner: Runner
    processes: Processes
    compose: Compose
    probe: Probe
    clock: Clock
    host_info: HostInfo
    registry: PackageRegistry
    data_dirs: DataDirs
