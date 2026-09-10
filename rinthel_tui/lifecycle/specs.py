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


def _wait_spec(service: LocalProcessService | DockerComposeService) -> PhaseSpec:
    # Mismo phase_wait_ready para los dos tipos de servicio — ver
    # managed_service._ServiceBase, de donde ambos heredan los campos de
    # ready/poll.
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
# Configura, no bootea — termina indicando que uses [1] BOOT. PREFLIGHT
# corre siempre primero; después, los steps de cada InstallUnit con
# enabled_of(cfg) en True (ver install.INSTALL_UNITS) — un servicio
# deshabilitado no aparece acá, numerado dinámicamente igual que RELOAD.
def install_phases(cfg: RinthelConfig) -> list[PhaseSpec]:
    raw = [PhaseSpec("◈ PREFLIGHT — GPU/CUDA/cmake/docker", install.phase_install_preflight)]
    for unit in install.INSTALL_UNITS:
        if not unit.enabled_of(cfg):
            continue
        raw.extend(PhaseSpec(f"◈ {label}", fn) for label, fn in unit.steps)
    return _renumbered(raw, len(raw), start=1)

# ── BOOT (rinthel-up.sh) ──────────────────────────────────────
# Funciones de ``cfg``, no constantes de módulo: cada servicio con
# ``enabled_of(cfg)`` en False queda afuera de las 4 secuencias (spawn/kill/
# up/down y su wait correspondiente), sin tocar nada más.
def boot_phases(cfg: RinthelConfig) -> list[PhaseSpec]:
    local = [s for s in services.LOCAL_SERVICES if s.enabled_of(cfg)]
    docker = [s for s in services.DOCKER_SERVICES if s.enabled_of(cfg)]
    return [
        PhaseSpec("◈ DOCKER", phases.phase_check_docker),
        *[spec for svc in local for spec in (_spawn_spec(svc), _wait_spec(svc))],
        *[spec for svc in docker for spec in (_up_spec(svc), _wait_spec(svc))],
    ]


# ── DOWN (rinthel-down.sh) ────────────────────────────────────
def down_phases(cfg: RinthelConfig) -> list[PhaseSpec]:
    local = [s for s in services.LOCAL_SERVICES if s.enabled_of(cfg)]
    docker = [s for s in services.DOCKER_SERVICES if s.enabled_of(cfg)]
    return [
        *[_kill_spec(svc) for svc in local],
        *[_down_spec(svc) for svc in docker],
    ]


# ── RELOAD (rinthel-reload.sh) — 3 tandas: shutdown → boot → rebuild+up ───
def _reload_raw_groups(cfg: RinthelConfig) -> tuple[list[PhaseSpec], list[PhaseSpec], list[PhaseSpec]]:
    local = [s for s in services.LOCAL_SERVICES if s.enabled_of(cfg)]
    docker = [s for s in services.DOCKER_SERVICES if s.enabled_of(cfg)]

    shutdown = [
        *[_kill_spec(svc) for svc in local],
        *[_down_spec(svc) for svc in docker],
    ]
    # Solo tiene sentido esperar el puerto de llama-server libre si vamos a
    # relanzarlo más abajo en boot_raw — si está deshabilitado, nadie lo
    # mató ni nadie lo va a levantar.
    if services.LLAMA_SERVICE.enabled_of(cfg):
        shutdown.append(
            PhaseSpec(
                f"◈ PUERTO {services.LLAMA_SERVICE.wait_label} LIBRE",
                managed_service.phase_wait_port_free,
                {"port_of": services.LLAMA_SERVICE.port_of},
            )
        )

    boot = [
        PhaseSpec("◈ DOCKER", phases.phase_check_docker),
        *[spec for svc in local for spec in (_spawn_spec(svc), _wait_spec(svc))],
    ]
    rebuild = [
        spec for svc in docker for spec in (_up_spec(svc, no_cache=True), _wait_spec(svc))
    ]
    return shutdown, boot, rebuild


def reload_phases(cfg: RinthelConfig) -> tuple[list[PhaseSpec], list[PhaseSpec], list[PhaseSpec]]:
    """Las 3 tandas de RELOAD, numeradas de punta a punta (``[i/N]``) sobre
    solo los servicios con ``enabled_of(cfg)`` en True — agregar/sacar un
    servicio, o deshabilitar uno, renumera sola sin tocar nada a mano."""
    shutdown, boot, rebuild = _reload_raw_groups(cfg)
    total = len(shutdown) + len(boot) + len(rebuild)
    return (
        _renumbered(shutdown, total, start=1),
        _renumbered(boot, total, start=1 + len(shutdown)),
        _renumbered(rebuild, total, start=1 + len(shutdown) + len(boot)),
    )
