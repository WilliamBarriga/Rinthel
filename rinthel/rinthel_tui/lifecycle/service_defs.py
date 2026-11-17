"""The "managed service" definitions: what each service is and how it is
derived from the config. ``LocalProcessService`` describes a local binary
(port, log, how to build its ``argv`` from ``cfg``); ``DockerComposeService``,
a service of a ``docker compose`` stack. The concrete instances
(LLAMA_SERVICE, etc.) live in ``services.py``, built from the
``config.py`` sub-configs.

A definition knows ``RinthelConfig`` and the phases do not: ``spec(cfg)``
turns it into the ready-built ``LocalProcessSpec``/``DockerComposeSpec`` that
the phases of ``lifecycle/domain/phases/service_phases.py`` receive. The menu
labels (``menu_label``, ``wait_label``, ``kill_label``) feed the
``PhaseSpec`` of ``specs.py`` and do not travel to the domain.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from rinthel_tui.config import RinthelConfig
from rinthel_tui.lifecycle.domain.types import ComposeService, DockerComposeSpec, LocalProcessSpec

# ── fields shared by LocalProcessService and DockerComposeService ────────
#
# Both service types are awaited the same way (wait_ready polls ready_url with
# the same backoff) and listed the same way in menu/report, so that subset of
# fields lives here once.
# kw_only=True because the subclasses add their own required fields
# (build_argv/log_of, dir_of/compose_service_name) after the ones that already
# have a default here — without kw_only, a dataclass does not allow it.


@dataclass(frozen=True, kw_only=True)
class _ServiceBase:
    # display_name: used in report messages ("llama-server murió al
    # instante"). menu_label/wait_label/kill_label: text of the PhaseSpec in
    # specs.py — separate from display_name because they do not always match
    # (e.g. "LLAMA-SERVER  --  Qwen3.6" in the menu vs. "llama-server" in the
    # messages).
    display_name: str
    menu_label: str
    wait_label: str
    kill_label: str
    # None for a service without its own port.
    port_of: Callable[[RinthelConfig], int] | None = None
    # Filters the service out of INSTALL/BOOT/TERMINATE/RELOAD when it returns
    # False (see ``specs.py``) — default True because today all 5
    # services always run.
    enabled_of: Callable[[RinthelConfig], bool] = lambda cfg: True
    # None for a DockerComposeService that exposes no HTTP healthcheck of its
    # own — phase_wait_ready has nothing to poll there and returns right away.
    ready_url_of: Callable[[RinthelConfig], str] | None = None
    default_ready_timeout: int = 90
    # Exponential backoff of the wait_ready polling: starts at
    # ready_poll_interval, is multiplied by ready_poll_backoff on each
    # round without a response, capped at ready_poll_max_interval — avoids
    # polling every fixed N seconds for the whole timeout when the service
    # is slow to come up (e.g. loading a large model).
    ready_poll_interval: float = 2.0
    ready_poll_backoff: float = 1.5
    ready_poll_max_interval: float = 10.0
    # Extra context line after a wait_ready timeout — only llama-server has
    # one today ("Levanta el modelo local antes de usar understory.").
    on_timeout_hint: str | None = None

    def _shared(self, cfg: RinthelConfig) -> dict:
        """The ``ServiceSpec`` fields, evaluated against ``cfg``."""
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
    # Variables the process receives on top of the daemon's environment.
    env_of: Callable[[RinthelConfig], dict[str, str]] = lambda cfg: {}
    # Files the process reads at startup, derived from the config (e.g.
    # audio.cpp's ``server.json``): rewritten on every spawn.
    files_of: Callable[[RinthelConfig], dict[Path, str]] = lambda cfg: {}
    # Directories the process needs to exist at startup (e.g.
    # llama-server's ``--slot-save-path``).
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
    # Only the portal rebuilds its image before coming up.
    build_args: tuple[str, ...] | None = None
    # (build arg, npm package): the build receives the package's latest
    # published version. With the Docker cache on, this is what rebuilds the
    # layer that installs ``@latest`` when a new version ships, and only then.
    npm_build_args: tuple[tuple[str, str], ...] = ()
    # The service's compose profile: without it active, the whole project's
    # ``up -d`` (that of any other service) does not bring it up.
    profile: str | None = None
    # Docker stacks come up faster than llama-server loading a large
    # model — overrides the 90s default of _ServiceBase.
    default_ready_timeout: int = 60

    def spec(self, cfg: RinthelConfig) -> DockerComposeSpec:
        return DockerComposeSpec(
            **self._shared(cfg),
            stack=ComposeService(self.dir_of(cfg), self.compose_service_name, self.profile, self.extra_env_of(cfg)),
            build_args=self.build_args,
            npm_build_args=self.npm_build_args,
        )
