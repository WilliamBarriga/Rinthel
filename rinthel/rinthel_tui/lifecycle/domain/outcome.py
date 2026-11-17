"""Cómo una phase le cuenta al admin lo que hace (``PhaseReport``) y lo que
hace con el ``RunResult`` de un comando: transmitir su salida y, si terminó
con error, contárselo y cortar. Un solo lugar para ese patrón, en vez de
repetirlo en cada phase."""

from typing import Protocol

from rinthel_tui.lifecycle.domain.errors import PhaseError
from rinthel_tui.lifecycle.domain.types import RunResult


class PhaseReport(Protocol):
    """Por dónde una fase le cuenta al admin lo que hace. Es texto libre: no
    es contrato (ADR 0005, regla 4)."""

    def info(self, msg: str) -> None: ...
    def success(self, msg: str) -> None: ...
    def warn(self, msg: str) -> None: ...
    def error(self, msg: str) -> None: ...


def report_output(report: PhaseReport, result: RunResult) -> None:
    """La salida de un comando es ruido de proceso: se transmite como info."""
    if result.output.strip():
        report.info(result.output.rstrip())


def fail_on_error(report: PhaseReport, result: RunResult, *, failed: str, error: str, hint: str = "") -> None:
    """Con un ``rc`` distinto de cero, reporta ``failed`` (más ``hint``, que el
    admin lee) y levanta ``PhaseError(error)``; los dos llevan el ``rc``."""
    if result.rc != 0:
        report.error(f"{failed} (rc {result.rc}){hint}")
        raise PhaseError(f"{error} (rc {result.rc})")


def require_ok(report: PhaseReport, result: RunResult, *, failed: str, error: str, hint: str = "") -> None:
    """Transmite la salida del comando y después ``fail_on_error``."""
    report_output(report, result)
    fail_on_error(report, result, failed=failed, error=error, hint=hint)
