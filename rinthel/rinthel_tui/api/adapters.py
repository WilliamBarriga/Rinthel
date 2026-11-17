"""Los adapters que ``create_app`` enchufa en cada puerto (ADR 0004): un
solo ``Adapters``, un campo por módulo. ``Adapters.from_cfg`` arma los reales;
los tests arman el suyo y cambian adapters así, nunca con monkeypatch."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

from rinthel_tui.clock import Clock, SystemClock
from rinthel_tui.config import RinthelConfig
from rinthel_tui.identity.adapters.deck_http import HttpDeckSessions
from rinthel_tui.identity.adapters.sqlite import SqliteIdentity
from rinthel_tui.identity.domain.ports import DeckSessions, Identity
from rinthel_tui.lifecycle.composition import real_host
from rinthel_tui.lifecycle.domain.host import Host
from rinthel_tui.models.composition import ModelAdapters
from rinthel_tui.models.domain import models as local_models
from rinthel_tui.monitoring.adapters.docker_compose import DockerComposeContainers
from rinthel_tui.monitoring.adapters.log_file import FileLog
from rinthel_tui.monitoring.adapters.managed_services import ManagedServicesSensor
from rinthel_tui.monitoring.adapters.nvidia_smi import NvidiaSmiGpu
from rinthel_tui.monitoring.adapters.psutil_host import PsutilHost
from rinthel_tui.monitoring.domain.monitor import TelemetrySources


@dataclass(frozen=True)
class Adapters:
    """Todo lo que ``create_app`` enchufa, un campo por módulo."""

    telemetry: TelemetrySources
    # El host donde corren las phases de lifecycle (``executor.bound_to``).
    lifecycle_host: Host
    # Users and Panel tokens, on ``rinthel.db`` (ADR 0007).
    identity: Identity
    # Catálogo, modelo activo y turnos en curso de los Local models.
    models: ModelAdapters
    # Deck's Sessions, retired before a user is deleted; ``None`` while Deck
    # is disabled (no Sessions to retire).
    deck_sessions: DeckSessions | None = None
    # El reloj de la app: lo comparten el Monitor y los casos de uso que
    # sellan instantes. Un test que quiere fijar el tiempo pasa un ``ManualClock``.
    clock: Clock = field(default_factory=SystemClock)

    @classmethod
    def from_cfg(cls, *, cfg_of: Callable[[], RinthelConfig]) -> Adapters:
        """``cfg_of`` es el ``cfg`` vivo de la app: por eso los arma
        ``create_app`` cuando no le pasan otros."""
        host = real_host()
        cfg = cfg_of()
        models = ModelAdapters.real(cfg_of)
        return cls(
            telemetry=real_telemetry(cfg_of, host, models),
            lifecycle_host=host,
            identity=SqliteIdentity(cfg.instance.database_path, clock=host.clock),
            deck_sessions=real_deck_sessions(cfg),
            models=models,
            clock=host.clock,
        )


def real_deck_sessions(cfg: RinthelConfig) -> DeckSessions | None:
    """Deck on the host loopback (host network on Linux, published port on
    Windows) with the Instance's service secret; ``None`` while Deck is
    disabled. Read once at startup, like the identity database: a new port or
    a rotated service secret takes effect when the daemon restarts, as it does
    for Deck itself. The client lives as long as the process."""
    if not cfg.deck.enabled:
        return None
    client = httpx.Client(base_url=f"http://127.0.0.1:{cfg.deck.port}", timeout=httpx.Timeout(10.0))
    return HttpDeckSessions(client, service_secret=cfg.secrets.service)


def real_telemetry(cfg_of: Callable[[], RinthelConfig], host: Host, models: ModelAdapters) -> TelemetrySources:
    """Las fuentes de telemetría del host. ``cfg_of`` es el ``cfg`` vivo:
    un ``POST /config`` reemplaza ``app.state.cfg`` y la próxima muestra (o
    la próxima conexión, para el log) ya lo ve. ``models`` da el catálogo y
    los ids activos que ``models_status`` resuelve en cada muestra."""

    def resolve(capability: str) -> tuple[str | None, str | None]:
        active = local_models.resolve(models.catalog, models.active, capability)  # type: ignore[arg-type]
        return active.id, active.warning

    return TelemetrySources(
        gpu=NvidiaSmiGpu(),
        host=PsutilHost(),
        containers=DockerComposeContainers(cfg_of),
        log=FileLog(cfg_of),
        models=ManagedServicesSensor(cfg_of, resolve, host.probe.http_ok),
    )
