"""Listas declarativas de fases — reemplaza los arrays RINTHEL_*_PHASES de
rinthel-up.sh/rinthel-down.sh/rinthel-reload.sh.

BOOT/DOWN/RELOAD se arman iterando ``services.LOCAL_SERVICES``/
``services.DOCKER_SERVICES`` — agregar o sacar un servicio ahí (más su
instancia en ``services.py``) alcanza para que las 4 secuencias lo
reflejen, renumeración de RELOAD incluida, sin tocar este archivo a mano.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from rinthel_tui.config import RinthelConfig
from rinthel_tui.lifecycle import install, managed_service, phases, services
from rinthel_tui.lifecycle.managed_service import DockerComposeService, LocalProcessService
from rinthel_tui.lifecycle.types import PhaseReport

PhaseFn = Callable[..., Coroutine[Any, Any, None]]


@dataclass(frozen=True)
class PhaseSpec:
    label: str
    fn: PhaseFn
    kwargs: dict[str, Any] = field(default_factory=dict)

    async def run(self, cfg: RinthelConfig, report: PhaseReport) -> None:
        await self.fn(cfg, report, **self.kwargs)


# ── builders de PhaseSpec por servicio — un solo lugar que sabe qué label
# y qué kwargs le corresponden a cada tipo de fase ────────────────────────


def _spawn_spec(service: LocalProcessService) -> PhaseSpec:
    return PhaseSpec(f"◈ {service.menu_label}", managed_service.phase_spawn, {"service": service})


def _wait_spec(service: LocalProcessService) -> PhaseSpec:
    return PhaseSpec(
        f"◈ ESPERANDO {service.wait_label}", managed_service.phase_wait_ready, {"service": service}
    )


def _kill_spec(service: LocalProcessService) -> PhaseSpec:
    return PhaseSpec(f"◈ {service.kill_label}", managed_service.phase_kill, {"service": service})


def _up_spec(service: DockerComposeService, *, no_cache: bool = False) -> PhaseSpec:
    return PhaseSpec(
        f"◈ {service.menu_label}",
        managed_service.phase_up,
        {"service": service, "no_cache": no_cache},
    )


def _wait_docker_spec(service: DockerComposeService) -> PhaseSpec:
    return PhaseSpec(
        f"◈ ESPERANDO {service.wait_label}",
        managed_service.phase_wait_ready_docker,
        {"service": service},
    )


def _down_spec(service: DockerComposeService) -> PhaseSpec:
    return PhaseSpec(f"◈ {service.kill_label}", managed_service.phase_down, {"service": service})


def _renumbered(specs: list[PhaseSpec], total: int, start: int) -> list[PhaseSpec]:
    """RELOAD numera las fases de punta a punta ("[i/total]") a través de
    sus 3 tandas — total/posición se calculan solos a partir de cuántos
    servicios haya en LOCAL_SERVICES/DOCKER_SERVICES, así que agregar o
    sacar uno no exige renumerar nada a mano."""
    out = []
    for i, spec in enumerate(specs):
        label = spec.label.removeprefix("◈ ")
        out.append(PhaseSpec(f"◈ [{start + i}/{total}] {label}", spec.fn, spec.kwargs))
    return out


# ── INSTALL (bootstrap de infra en máquina nueva) ─────────────
# Configura, no bootea — termina indicando que uses [1] BOOT.
INSTALL_PHASES: list[PhaseSpec] = [
    PhaseSpec("◈ [1/6] PREFLIGHT — GPU/CUDA/cmake/docker", install.phase_install_preflight),
    PhaseSpec("◈ [2/6] LLAMA.CPP — clone", install.phase_install_clone_llamacpp),
    PhaseSpec("◈ [3/6] LLAMA.CPP — build CUDA (native)", install.phase_install_build_llamacpp),
    PhaseSpec("◈ [4/6] MODELO GGUF — descarga", install.phase_install_download_model),
    PhaseSpec("◈ [5/6] PITHAGORAS — clone + configurar", install.phase_install_setup_pithagoras),
    PhaseSpec("◈ [6/6] UNDERSTORY — scaffold + configurar", install.phase_install_setup_understory),
]

# ── BOOT (rinthel-up.sh) ──────────────────────────────────────
BOOT_PHASES: list[PhaseSpec] = [
    PhaseSpec("◈ DOCKER", phases.phase_check_docker),
    *[spec for svc in services.LOCAL_SERVICES for spec in (_spawn_spec(svc), _wait_spec(svc))],
    *[spec for svc in services.DOCKER_SERVICES for spec in (_up_spec(svc), _wait_docker_spec(svc))],
]

# ── DOWN (rinthel-down.sh) ────────────────────────────────────
DOWN_PHASES: list[PhaseSpec] = [
    *[_kill_spec(svc) for svc in services.LOCAL_SERVICES],
    *[_down_spec(svc) for svc in services.DOCKER_SERVICES],
]

# ── RELOAD (rinthel-reload.sh) — 3 tandas: shutdown → boot → rebuild+up ───
_shutdown_raw = [
    *[_kill_spec(svc) for svc in services.LOCAL_SERVICES],
    *[_down_spec(svc) for svc in services.DOCKER_SERVICES],
    PhaseSpec(
        f"◈ PUERTO {services.LLAMA_SERVICE.wait_label} LIBRE",
        managed_service.phase_wait_port_free,
        {"port_of": services.LLAMA_SERVICE.port_of},
    ),
]
_boot_raw = [
    PhaseSpec("◈ DOCKER", phases.phase_check_docker),
    *[spec for svc in services.LOCAL_SERVICES for spec in (_spawn_spec(svc), _wait_spec(svc))],
]
_rebuild_raw = [
    spec
    for svc in services.DOCKER_SERVICES
    for spec in (_up_spec(svc, no_cache=True), _wait_docker_spec(svc))
]

_RELOAD_TOTAL = len(_shutdown_raw) + len(_boot_raw) + len(_rebuild_raw)

RELOAD_SHUTDOWN_PHASES: list[PhaseSpec] = _renumbered(_shutdown_raw, _RELOAD_TOTAL, start=1)
RELOAD_BOOT_PHASES: list[PhaseSpec] = _renumbered(
    _boot_raw, _RELOAD_TOTAL, start=1 + len(_shutdown_raw)
)
RELOAD_REBUILD_PHASES: list[PhaseSpec] = _renumbered(
    _rebuild_raw, _RELOAD_TOTAL, start=1 + len(_shutdown_raw) + len(_boot_raw)
)
