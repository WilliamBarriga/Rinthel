"""Símbolos compartidos por todo lifecycle/ sin depender de nada más del
paquete — evita ciclos de import entre managed_service.py, phases.py,
runner.py, specs.py e install.py."""

from typing import Protocol


class PhaseError(Exception):
    """Fallo esperado de una fase (equivalente al `exit 1` de bash)."""


class PhaseReport(Protocol):
    def info(self, msg: str) -> None: ...
    def success(self, msg: str) -> None: ...
    def warn(self, msg: str) -> None: ...
    def error(self, msg: str) -> None: ...
