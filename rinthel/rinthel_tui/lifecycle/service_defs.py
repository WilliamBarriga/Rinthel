"""Las definiciones de "servicio gestionado": qué es cada servicio y cómo se
deriva de la config. ``LocalProcessService`` describe un binario local (puerto,
log, cómo armar su ``argv`` a partir de ``cfg``); ``DockerComposeService``, un
servicio de un stack ``docker compose``. Las instancias concretas
(LLAMA_SERVICE, etc.) viven en ``services.py``, construidas a partir de los
sub-configs de ``config.py``.

Una definición conoce a ``RinthelConfig`` y las phases no: ``spec(cfg)`` la
convierte en el ``LocalProcessSpec``/``DockerComposeSpec`` ya armado que
reciben las phases de ``lifecycle/domain/phases/service_phases.py``. Los
labels del menú (``menu_label``, ``wait_label``, ``kill_label``) alimentan los
``PhaseSpec`` de ``specs.py`` y no viajan al dominio.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from rinthel_tui.config import RinthelConfig
from rinthel_tui.lifecycle.domain.types import ComposeService, DockerComposeSpec, LocalProcessSpec

# ── campos compartidos por LocalProcessService y DockerComposeService ────
#
# Ambos tipos de servicio se esperan igual (wait_ready pollea ready_url con el
# mismo backoff) y se listan igual en menú/report, así que ese subconjunto de
# campos vive acá una sola vez.
# kw_only=True porque las subclases suman sus propios campos requeridos
# (build_argv/log_of, dir_of/compose_service_name) después de los que ya
# tienen default acá — sin kw_only, un dataclass no lo permite.


@dataclass(frozen=True, kw_only=True)
class _ServiceBase:
    # display_name: usado en los mensajes de report ("llama-server murió al
    # instante"). menu_label/wait_label/kill_label: texto de los PhaseSpec en
    # specs.py — separados de display_name porque no siempre coinciden (ej.
    # "LLAMA-SERVER  --  Qwen3.6" en el menú vs. "llama-server" en los
    # mensajes).
    display_name: str
    menu_label: str
    wait_label: str
    kill_label: str
    # None en un servicio sin puerto propio.
    port_of: Callable[[RinthelConfig], int] | None = None
    # Filtra el servicio de INSTALL/BOOT/TERMINATE/RELOAD cuando da False (ver
    # ``specs.py``) — default True porque hoy los 5
    # servicios corren siempre.
    enabled_of: Callable[[RinthelConfig], bool] = lambda cfg: True
    # None en un DockerComposeService que no expone healthcheck HTTP propio
    # — phase_wait_ready no tiene nada que pollear ahí y vuelve al toque.
    ready_url_of: Callable[[RinthelConfig], str] | None = None
    default_ready_timeout: int = 90
    # Backoff exponencial del polling de wait_ready: arranca en
    # ready_poll_interval, se multiplica por ready_poll_backoff en cada
    # vuelta sin respuesta, capeado en ready_poll_max_interval — evita
    # pollear cada N segundos fijos durante todo el timeout cuando el
    # servicio tarda en levantar (ej. carga de un modelo grande).
    ready_poll_interval: float = 2.0
    ready_poll_backoff: float = 1.5
    ready_poll_max_interval: float = 10.0
    # Línea extra de contexto tras un timeout de wait_ready — solo llama-server
    # la tiene hoy ("Levanta el modelo local antes de usar understory.").
    on_timeout_hint: str | None = None

    def _shared(self, cfg: RinthelConfig) -> dict:
        """Los campos de ``ServiceSpec``, evaluados contra ``cfg``."""
        return {
            "display_name": self.display_name,
            "port": self.port_of(cfg) if self.port_of is not None else None,
            "enabled": self.enabled_of(cfg),
            "ready_url": self.ready_url_of(cfg) if self.ready_url_of is not None else None,
            "ready_timeout": self.default_ready_timeout,
            "ready_poll_interval": self.ready_poll_interval,
            "ready_poll_backoff": self.ready_poll_backoff,
            "ready_poll_max_interval": self.ready_poll_max_interval,
            "on_timeout_hint": self.on_timeout_hint,
        }


# ── LocalProcessService: llama-server ───────────────────────────────────


@dataclass(frozen=True, kw_only=True)
class LocalProcessService(_ServiceBase):
    build_argv: Callable[[RinthelConfig], list[str]]
    log_of: Callable[[RinthelConfig], Path]
    # Variables que el proceso recibe además del entorno del daemon.
    env_of: Callable[[RinthelConfig], dict[str, str]] = lambda cfg: {}
    # Archivos que el proceso lee al arrancar, derivados de la config (p. ej.
    # el ``server.json`` de audio.cpp): se reescriben en cada spawn.
    files_of: Callable[[RinthelConfig], dict[Path, str]] = lambda cfg: {}
    # Directorios que el proceso necesita existentes al arrancar (p. ej. el
    # ``--slot-save-path`` de llama-server).
    dirs_of: Callable[[RinthelConfig], list[Path]] = lambda cfg: []

    def spec(self, cfg: RinthelConfig) -> LocalProcessSpec:
        return LocalProcessSpec(
            **self._shared(cfg),
            argv=tuple(self.build_argv(cfg)),
            log=self.log_of(cfg),
            env=self.env_of(cfg),
            files=self.files_of(cfg),
            dirs=tuple(self.dirs_of(cfg)),
        )


# ── DockerComposeService: Understory / portal ─────────────────────────


@dataclass(frozen=True, kw_only=True)
class DockerComposeService(_ServiceBase):
    dir_of: Callable[[RinthelConfig], Path]
    compose_service_name: str
    extra_env_of: Callable[[RinthelConfig], dict[str, str]] = lambda cfg: {}
    # Solo el portal rebuildea su imagen antes de levantar.
    build_args: tuple[str, ...] | None = None
    # (build arg, paquete npm): el build recibe la última versión publicada
    # del paquete. Con el cache de Docker prendido, es lo que rehace la capa
    # que instala ``@latest`` cuando sale una versión nueva, y solo entonces.
    npm_build_args: tuple[tuple[str, str], ...] = ()
    # Profile de compose del servicio: sin él activo, el ``up -d`` del
    # proyecto entero (el de cualquier otro servicio) no lo levanta.
    profile: str | None = None
    # Los stacks docker tardan menos en levantar que llama-server cargando
    # un modelo grande — pisa el default de 90s de _ServiceBase.
    default_ready_timeout: int = 60

    def spec(self, cfg: RinthelConfig) -> DockerComposeSpec:
        return DockerComposeSpec(
            **self._shared(cfg),
            stack=ComposeService(self.dir_of(cfg), self.compose_service_name, self.profile, self.extra_env_of(cfg)),
            build_args=self.build_args,
            npm_build_args=self.npm_build_args,
        )
