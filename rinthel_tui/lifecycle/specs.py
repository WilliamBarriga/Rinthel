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


# ── INSTALL agrupado por unidad instalable (daemon FastAPI, sesión 07 del
# port-map) — mismo criterio que boot_units/reload_units: un ServiceOutcome
# por unidad en vez de un resultado por fase. PREFLIGHT es su propia unidad
# (no es de ningún InstallUnit, mismo motivo que el chequeo de DOCKER queda
# aparte en boot_units) — a diferencia de ese chequeo, acá no hace falta que
# el daemon lo intercale aparte: no hay nada que deba correr antes de
# PREFLIGHT. No numera nada (igual que boot_units/reload_units) —
# install_phases (arriba) sigue siendo la fuente del checklist numerado que
# usa Textual.
def install_units(cfg: RinthelConfig) -> list[tuple[str, list[PhaseSpec]]]:
    units: list[tuple[str, list[PhaseSpec]]] = [
        ("preflight", [PhaseSpec("◈ PREFLIGHT — GPU/CUDA/cmake/docker", install.phase_install_preflight)])
    ]
    for unit in install.INSTALL_UNITS:
        if not unit.enabled_of(cfg):
            continue
        units.append((unit.label.lower(), [PhaseSpec(f"◈ {label}", fn) for label, fn in unit.steps]))
    return units


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


# ── BOOT/DOWN agrupados por servicio (daemon FastAPI, ticket 04) ─────────
# boot_phases/down_phases de arriba dan una lista PLANA de fases — le sirve
# a phase_runner.py (TUI) para pintar un checklist fase por fase. El daemon
# necesita lo contrario: un solo ServiceOutcome por servicio en la respuesta
# de POST /boot y /terminate (wire shape fijado en docs/adr/0001), aunque
# boot corra 2 fases por servicio (spawn+wait / up+wait) y down corra 1
# (kill / down). *_units agrupa eso — (slug, [fases del servicio]) — sin
# duplicar la lógica de habilitado/orden que ya vive arriba.
def boot_units(cfg: RinthelConfig) -> list[tuple[str, list[PhaseSpec]]]:
    """Como boot_phases, pero agrupada por servicio en vez de en una lista
    plana. No incluye el chequeo de DOCKER (phases.phase_check_docker): ese
    no es de ningún servicio — el caller (daemon.py) lo corre aparte, antes
    de esto, y le da su propio ServiceOutcome (service="docker")."""
    local = [s for s in services.LOCAL_SERVICES if s.enabled_of(cfg)]
    docker = [s for s in services.DOCKER_SERVICES if s.enabled_of(cfg)]
    return [
        *[(svc.display_name.lower(), [_spawn_spec(svc), _wait_spec(svc)]) for svc in local],
        *[(svc.display_name.lower(), [_up_spec(svc), _wait_spec(svc)]) for svc in docker],
    ]


def down_units(cfg: RinthelConfig) -> list[tuple[str, list[PhaseSpec]]]:
    """Igual que down_phases, agrupada por servicio — acá ya es 1:1 (una
    sola fase por servicio), pero se expone así para que el daemon use la
    misma forma (slug, [fases]) que boot_units en vez de dos formatos
    distintos según el comando."""
    local = [s for s in services.LOCAL_SERVICES if s.enabled_of(cfg)]
    docker = [s for s in services.DOCKER_SERVICES if s.enabled_of(cfg)]
    return [
        *[(svc.display_name.lower(), [_kill_spec(svc)]) for svc in local],
        *[(svc.display_name.lower(), [_down_spec(svc)]) for svc in docker],
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


# ── RELOAD agrupado por servicio (daemon FastAPI, sesión 06 del port-map) ──
# Mismo criterio que boot_units/down_units: un ServiceOutcome por unidad en
# vez de un resultado por fase — pero acá en 3 tandas en secuencia
# (shutdown → boot → rebuild) en vez de una sola lista plana. No numera nada
# (a diferencia de reload_phases, que sí lo hace para el checklist de
# Textual): el daemon no pinta checklist, solo necesita qué corrió y si
# salió bien. Igual que boot_units, no incluye el chequeo de DOCKER — el
# caller (daemon.py) lo corre aparte, entre las tandas shutdown y boot.
def reload_units(
    cfg: RinthelConfig,
) -> tuple[list[tuple[str, list[PhaseSpec]]], list[tuple[str, list[PhaseSpec]]], list[tuple[str, list[PhaseSpec]]]]:
    local = [s for s in services.LOCAL_SERVICES if s.enabled_of(cfg)]
    docker = [s for s in services.DOCKER_SERVICES if s.enabled_of(cfg)]

    shutdown: list[tuple[str, list[PhaseSpec]]] = [
        *[(svc.display_name.lower(), [_kill_spec(svc)]) for svc in local],
        *[(svc.display_name.lower(), [_down_spec(svc)]) for svc in docker],
    ]
    # Mismo guard que _reload_raw_groups: solo tiene sentido esperar el
    # puerto libre si el boot que sigue va a relanzar llama-server.
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
