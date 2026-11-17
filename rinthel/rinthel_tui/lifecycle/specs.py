"""Listas declarativas de fases — reemplaza los arrays RINTHEL_*_PHASES de
rinthel-up.sh/rinthel-down.sh/rinthel-reload.sh.

BOOT/DOWN/RELOAD se arman iterando ``services.LOCAL_SERVICES``/
``services.DOCKER_SERVICES`` — agregar o sacar un servicio ahí (más su
instancia en ``services.py``) alcanza para que las 4 secuencias lo
reflejen sin tocar este archivo a mano.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from rinthel_tui.config import RinthelConfig
from rinthel_tui.lifecycle import install, managed_service, services
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


# ── INSTALL agrupado por unidad instalable — mismo criterio que
# boot_units/reload_units: un ServiceOutcome por unidad en vez de un
# resultado por fase. PREFLIGHT es su propia unidad (no es de ningún
# InstallUnit, mismo motivo que el chequeo de DOCKER queda aparte en
# boot_units) — a diferencia de ese chequeo, acá no hace falta que el
# daemon lo intercale aparte: no hay nada que deba correr antes de
# PREFLIGHT. No numera nada: el daemon no pinta checklist, solo necesita
# qué corrió y si salió bien.
def install_units(cfg: RinthelConfig) -> list[tuple[str, list[PhaseSpec]]]:
    units: list[tuple[str, list[PhaseSpec]]] = [
        ("preflight", [PhaseSpec("◈ PREFLIGHT — GPU/CUDA/cmake/docker", install.phase_install_preflight)])
    ]
    for unit in install.INSTALL_UNITS:
        if not unit.enabled_of(cfg):
            continue
        units.append((unit.label.lower(), [PhaseSpec(f"◈ {label}", fn) for label, fn in unit.steps]))
    return units


# ── BOOT/DOWN agrupados por servicio ──────────────────────────────────────
# El daemon necesita un solo ServiceOutcome por servicio en la respuesta de
# POST /boot y /terminate (wire shape fijado en docs/adr/0001), aunque boot
# corra 2 fases por servicio (spawn+wait / up+wait) y down corra 1 (kill /
# down). *_units agrupa eso — (slug, [fases del servicio]) — sin duplicar la
# lógica de habilitado/orden que ya vive arriba.
def boot_units(cfg: RinthelConfig) -> list[tuple[str, list[PhaseSpec]]]:
    """Un ServiceOutcome por servicio en vez de un resultado por fase. No
    incluye el chequeo de DOCKER (phases.phase_check_docker): ese no es de
    ningún servicio — el caller (daemon.py) lo corre aparte, antes de esto,
    y le da su propio ServiceOutcome (service="docker")."""
    local = [s for s in services.LOCAL_SERVICES if s.enabled_of(cfg)]
    docker = [s for s in services.DOCKER_SERVICES if s.enabled_of(cfg)]
    return [
        *[(svc.display_name.lower(), [_spawn_spec(svc), _wait_spec(svc)]) for svc in local],
        *[(svc.display_name.lower(), [_up_spec(svc), _wait_spec(svc)]) for svc in docker],
    ]


def down_units(cfg: RinthelConfig) -> list[tuple[str, list[PhaseSpec]]]:
    """Acá ya es 1:1 (una sola fase por servicio), pero se expone así para
    que el daemon use la misma forma (slug, [fases]) que boot_units en vez
    de dos formatos distintos según el comando."""
    local = [s for s in services.LOCAL_SERVICES if s.enabled_of(cfg)]
    docker = [s for s in services.DOCKER_SERVICES if s.enabled_of(cfg)]
    return [
        *[(svc.display_name.lower(), [_kill_spec(svc)]) for svc in local],
        *[(svc.display_name.lower(), [_down_spec(svc)]) for svc in docker],
    ]


# ── RELOAD agrupado por servicio ──────────────────────────────────────────
# Mismo criterio que boot_units/down_units: un ServiceOutcome por unidad en
# vez de un resultado por fase — pero acá en 3 tandas en secuencia
# (shutdown → boot → rebuild). No numera nada: el daemon no pinta checklist,
# solo necesita qué corrió y si salió bien. Igual que boot_units, no incluye
# el chequeo de DOCKER — el caller (daemon.py) lo corre aparte, entre las
# tandas shutdown y boot.
def reload_units(
    cfg: RinthelConfig,
) -> tuple[list[tuple[str, list[PhaseSpec]]], list[tuple[str, list[PhaseSpec]]], list[tuple[str, list[PhaseSpec]]]]:
    local = [s for s in services.LOCAL_SERVICES if s.enabled_of(cfg)]
    docker = [s for s in services.DOCKER_SERVICES if s.enabled_of(cfg)]

    shutdown: list[tuple[str, list[PhaseSpec]]] = [
        *[(svc.display_name.lower(), [_kill_spec(svc)]) for svc in local],
        *[(svc.display_name.lower(), [_down_spec(svc)]) for svc in docker],
    ]
    # Solo tiene sentido esperar el puerto de llama-server libre si vamos a
    # relanzarlo más abajo en boot — si está deshabilitado, nadie lo mató ni
    # nadie lo va a levantar.
    if services.LLAMA_SERVICE.enabled_of(cfg):
        shutdown.append((
            services.LLAMA_SERVICE.display_name.lower(),
            [
                PhaseSpec(
                    f"◈ PUERTO {services.LLAMA_SERVICE.wait_label} LIBRE",
                    managed_service.phase_wait_port_free,
                    {"port_of": services.LLAMA_SERVICE.port_of},
                )
            ],
        ))

    boot = [(svc.display_name.lower(), [_spawn_spec(svc), _wait_spec(svc)]) for svc in local]
    rebuild = [(svc.display_name.lower(), [_up_spec(svc, no_cache=True), _wait_spec(svc)]) for svc in docker]

    return shutdown, boot, rebuild
