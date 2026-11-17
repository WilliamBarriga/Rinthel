"""Los adapters que ``create_app`` enchufa en cada puerto (ADR 0004): un
solo ``Adapters``, un campo por módulo. ``Adapters.from_cfg`` arma los reales;
los tests arman el suyo y cambian adapters así, nunca con monkeypatch."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from rinthel_tui.clock import Clock, SystemClock
from rinthel_tui.config import RinthelConfig
from rinthel_tui.lifecycle.composition import real_host
from rinthel_tui.lifecycle.domain.host import Host
from rinthel_tui.lifecycle.services import LLAMA_SERVICE
from rinthel_tui.models.composition import ModelAdapters
from rinthel_tui.monitoring.adapters.docker_compose import DockerComposeContainers
from rinthel_tui.monitoring.adapters.http_readiness import HttpReadiness
from rinthel_tui.monitoring.adapters.log_file import FileLog
from rinthel_tui.monitoring.adapters.nvidia_smi import NvidiaSmiGpu
from rinthel_tui.monitoring.adapters.psutil_host import PsutilHost
from rinthel_tui.monitoring.domain.monitor import TelemetrySources


@dataclass(frozen=True)
class Adapters:
    """Todo lo que ``create_app`` enchufa, un campo por módulo."""

    telemetry: TelemetrySources
    # El host donde corren las phases de lifecycle (``executor.bound_to``).
    lifecycle_host: Host
    # Catálogo, modelo activo y turnos en curso de los Local models.
    models: ModelAdapters
    # El reloj de la app: lo comparten el Monitor y los casos de uso que
    # sellan instantes. Un test que quiere fijar el tiempo pasa un ``ManualClock``.
    clock: Clock = field(default_factory=SystemClock)

    @classmethod
    def from_cfg(cls, *, cfg_of: Callable[[], RinthelConfig]) -> Adapters:
        """``cfg_of`` es el ``cfg`` vivo de la app: por eso los arma
        ``create_app`` cuando no le pasan otros."""
        host = real_host()
        return cls(
            telemetry=real_telemetry(cfg_of, host),
            lifecycle_host=host,
            models=ModelAdapters.real(cfg_of),
            clock=host.clock,
        )


def real_telemetry(cfg_of: Callable[[], RinthelConfig], host: Host) -> TelemetrySources:
    """Las fuentes de telemetría del host. ``cfg_of`` es el ``cfg`` vivo:
    un ``POST /config`` reemplaza ``app.state.cfg`` y la próxima muestra (o
    la próxima conexión, para el log) ya lo ve."""
    return TelemetrySources(
        gpu=NvidiaSmiGpu(),
        host=PsutilHost(),
        containers=DockerComposeContainers(cfg_of),
        log=FileLog(cfg_of),
        llama=HttpReadiness(lambda: _llama_ready_url(cfg_of()), host.probe.http_ok),
    )


def _llama_ready_url(cfg: RinthelConfig) -> str:
    url = LLAMA_SERVICE.spec(cfg).ready_url
    assert url is not None, "llama-server always declares its ready_url"
    return url
