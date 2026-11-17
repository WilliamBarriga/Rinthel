"""Lifecycle plans (ver GLOSSARY.md): qué corre cada comando — tandas
ordenadas, chequeo de DOCKER incluido y failure policy. Los corre
``executor.execute``.

BOOT/TERMINATE/RELOAD se arman iterando ``services.LOCAL_SERVICES``/
``services.DOCKER_SERVICES`` — agregar o sacar un servicio ahí (más su
instancia en ``services.py``) alcanza para que los planes lo reflejen sin
tocar este archivo a mano.
"""

from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any, Literal

from rinthel_tui.config import RinthelConfig
from rinthel_tui.lifecycle import install, services
from rinthel_tui.lifecycle.domain.host import Host
from rinthel_tui.lifecycle.domain.outcome import PhaseReport
from rinthel_tui.lifecycle.domain.phases import data_dir, docker, managed_service
from rinthel_tui.lifecycle.managed_service import DockerComposeService, LocalProcessService

PhaseFn = Callable[..., Coroutine[Any, Any, None]]


@dataclass(frozen=True)
class PhaseSpec:
    """Una fase del plan: ``fn(host, report, **kwargs)``. Lo que la fase necesita
    (el spec de un servicio, o la tarea de INSTALL) llega por ``kwargs``, ya
    atado por el builder del plan."""

    label: str
    fn: PhaseFn
    kwargs: dict[str, Any] = field(default_factory=dict)

    async def run(self, report: PhaseReport, host: Host) -> None:
        await self.fn(host, report, **self.kwargs)


@dataclass(frozen=True)
class Unit:
    """Las fases de una unidad — un ``ServiceOutcome`` en la respuesta."""

    service: str
    phases: tuple[PhaseSpec, ...]


@dataclass(frozen=True)
class Batch:
    """Tanda de unidades. ``marker`` se transmite como ``phase_batch`` al
    abrirla; ``None`` no transmite nada."""

    marker: str | None
    units: tuple[Unit, ...]


@dataclass(frozen=True)
class Plan:
    """Lifecycle plan: lo que corre un comando entero. ``on_failure`` es la
    failure policy del plan — "stop" corta en la primera unidad que falla,
    "continue" sigue con las que quedan."""

    on_failure: Literal["stop", "continue"]
    batches: tuple[Batch, ...]


# ── builders de PhaseSpec por servicio — un solo lugar que sabe qué label
# y qué kwargs le corresponden a cada tipo de fase ────────────────────────


def _spawn_spec(cfg: RinthelConfig, service: LocalProcessService) -> PhaseSpec:
    return PhaseSpec(f"◈ {service.menu_label}", managed_service.phase_spawn, {"service": service.spec(cfg)})


def _wait_spec(cfg: RinthelConfig, service: LocalProcessService | DockerComposeService) -> PhaseSpec:
    # Mismo phase_wait_ready para los dos tipos de servicio — ver
    # managed_service._ServiceBase, de donde ambos heredan los campos de
    # ready/poll.
    return PhaseSpec(f"◈ ESPERANDO {service.wait_label}", managed_service.phase_wait_ready, {"service": service.spec(cfg)})


def _kill_spec(cfg: RinthelConfig, service: LocalProcessService) -> PhaseSpec:
    return PhaseSpec(f"◈ {service.kill_label}", managed_service.phase_kill, {"service": service.spec(cfg)})


def _up_spec(cfg: RinthelConfig, service: DockerComposeService, *, rebuild: bool = False) -> PhaseSpec:
    return PhaseSpec(
        f"◈ {service.menu_label}",
        managed_service.phase_up,
        {"service": service.spec(cfg), "rebuild": rebuild},
    )


def _down_spec(cfg: RinthelConfig, service: DockerComposeService) -> PhaseSpec:
    return PhaseSpec(f"◈ {service.kill_label}", managed_service.phase_down, {"service": service.spec(cfg)})


# ── INSTALL ───────────────────────────────────────────────────────────────
# Un Unit por InstallUnit habilitada, más PREFLIGHT como Unit propio y
# primero: si falta CUDA/docker no tiene sentido seguir con clone/build/
# descarga. No numera labels: el daemon no pinta checklist, solo necesita qué
# corrió y si salió bien.
def _install_spec(cfg: RinthelConfig, step: install.InstallStep) -> PhaseSpec:
    return PhaseSpec(f"◈ {step.label}", step.fn, {"task": step.task(cfg)})


def install_plan(cfg: RinthelConfig, *, voice: bool = False) -> Plan:
    """``voice`` (INSTALL ``--voice``, opt-in) adds the voice unit last. Voice
    is Linux only: on Windows the unit is a notice and nothing else."""
    preflight = PhaseSpec("◈ PREFLIGHT — GPU/CUDA/cmake/docker", install.phase_install_preflight)
    units = [Unit("preflight", (preflight,))]
    for unit in install.INSTALL_UNITS:
        if unit.enabled_of(cfg):
            units.append(Unit(unit.label.lower(), tuple(_install_spec(cfg, step) for step in unit.steps)))
    if voice:
        unit = install.VOICE_INSTALL
        if cfg.platform == "linux":
            units.append(Unit(unit.label.lower(), tuple(_install_spec(cfg, step) for step in unit.steps)))
        else:
            notice = PhaseSpec(
                f"◈ {unit.label}  --  SOLO LINUX", managed_service.phase_notice,
                {"message": "la voz es solo de Linux: INSTALL la omite en esta Platform"},
            )
            units.append(Unit(unit.label.lower(), (notice,)))
    return Plan(on_failure="stop", batches=(Batch(marker=None, units=tuple(units)),))


# ── BOOT/TERMINATE ────────────────────────────────────────────────────────
# Un Unit por servicio: el daemon devuelve un ServiceOutcome por servicio en
# POST /boot y /terminate (wire shape fijado en docs/adr/0001), aunque boot
# corra 2 fases por servicio (spawn+wait / up+wait) y terminate 1 (kill /
# down). El chequeo de DOCKER es un Unit más ("docker"), primero en boot:
# si falla, boot no toca ningún servicio.


def _container_user(cfg: RinthelConfig) -> tuple[int, int]:
    """``PUID``/``PGID`` del ``.env``, con el 1000:1000 que compose usa si faltan."""
    instance = cfg.instance
    return int(instance.variable("PUID") or 1000), int(instance.variable("PGID") or 1000)


def _enabled_local(cfg: RinthelConfig) -> list[LocalProcessService]:
    return [s for s in services.LOCAL_SERVICES if s.enabled_of(cfg)]


def _enabled_docker(cfg: RinthelConfig) -> list[DockerComposeService]:
    return [s for s in services.DOCKER_SERVICES if s.enabled_of(cfg)]


def _local_unit(cfg: RinthelConfig, svc: LocalProcessService) -> Unit:
    if svc is services.LLAMA_SERVICE and cfg.local_model is None:
        # Sin Local model activo usable llama no arranca: el aviso queda en
        # el resultado del boot y el resto de los servicios sigue.
        notice = PhaseSpec(
            f"◈ {svc.menu_label}  --  SIN LOCAL MODEL ACTIVO",
            managed_service.phase_notice,
            {"message": cfg.model_warning or "sin Local model activo"},
        )
        return Unit(svc.display_name.lower(), (notice,))
    return Unit(svc.display_name.lower(), (_spawn_spec(cfg, svc), _wait_spec(cfg, svc)))


def restart_phases(cfg: RinthelConfig, service: LocalProcessService) -> tuple[PhaseSpec, ...]:
    """Parar lo que escuche en el puerto de ``service``, lanzarlo con el
    modelo de ``cfg`` y esperar a que responda. Cada paso es obligatorio: un
    puerto que no se libera o un modelo que no responde es un fallo."""
    spec = service.spec(cfg)
    return (
        PhaseSpec(f"◈ {service.kill_label}", managed_service.phase_kill, {"service": spec, "required": True}),
        _spawn_spec(cfg, service),
        PhaseSpec(f"◈ ESPERANDO {service.wait_label}", managed_service.phase_wait_ready, {"service": spec, "required": True}),
    )


def restart_plan(cfg: RinthelConfig, service: LocalProcessService) -> Plan:
    """El cambio de Local model de la Capability que sirve ``service``
    (``services.MODEL_SERVICES``): quien cambia decide el rollback."""
    unit = Unit(service.display_name.lower(), restart_phases(cfg, service))
    return Plan(on_failure="stop", batches=(Batch(marker=None, units=(unit,)),))


def stop_plan(cfg: RinthelConfig, service: LocalProcessService) -> Plan:
    """Apagar una Capability (``models off``): parar ``service`` por su
    puerto; un puerto que no se libera es un fallo."""
    kill = PhaseSpec(f"◈ {service.kill_label}", managed_service.phase_kill, {"service": service.spec(cfg), "required": True})
    return Plan(on_failure="stop", batches=(Batch(marker=None, units=(Unit(service.display_name.lower(), (kill,)),)),))


def _docker_unit(cfg: RinthelConfig, svc: DockerComposeService, *, rebuild: bool = False) -> Unit:
    """Un servicio compose: arriba y esperado. Deck, que corre con el usuario
    del host, antes de todo deja su volumen con el dueño del contenedor."""
    phases = [_up_spec(cfg, svc, rebuild=rebuild), _wait_spec(cfg, svc)]
    if svc is services.DECK_SERVICE:
        uid, gid = _container_user(cfg)
        data = PhaseSpec(
            "◈ DATOS DE DECK  --  DUEÑO DEL DIRECTORIO",
            data_dir.phase_ensure_data_dir,
            {"path": cfg.instance.deck_data_dir, "uid": uid, "gid": gid},
        )
        phases.insert(0, data)
    return Unit(svc.display_name.lower(), tuple(phases))


def _shutdown_units(cfg: RinthelConfig) -> tuple[Unit, ...]:
    """Lo comparten ``terminate_plan`` y el shutdown de ``reload_plan``."""
    return (
        *[Unit(svc.display_name.lower(), (_kill_spec(cfg, svc),)) for svc in _enabled_local(cfg)],
        *[Unit(svc.display_name.lower(), (_down_spec(cfg, svc),)) for svc in _enabled_docker(cfg)],
    )


def _docker_check_unit() -> Unit:
    return Unit("docker", (PhaseSpec("◈ DOCKER", docker.phase_check_docker),))


def boot_plan(cfg: RinthelConfig) -> Plan:
    units = (
        _docker_check_unit(),
        *[_local_unit(cfg, svc) for svc in _enabled_local(cfg)],
        *[_docker_unit(cfg, svc) for svc in _enabled_docker(cfg)],
    )
    return Plan(on_failure="stop", batches=(Batch(marker=None, units=units),))


def terminate_plan(cfg: RinthelConfig) -> Plan:
    """``continue``: terminate sigue con lo que queda aunque un servicio no
    se deje parar (GLOSSARY.md, Boot / Terminate)."""
    return Plan(on_failure="continue", batches=(Batch(marker=None, units=_shutdown_units(cfg)),))


# ── RELOAD ────────────────────────────────────────────────────────────────
# shutdown (sin marcador) → "boot" (DOCKER y los servicios locales) →
# "rebuild" (docker, build + up). Los marcadores viajan como ``phase_batch``
# para que el cliente sepa cuándo disparar sus transiciones (docs/adr/0001).
def reload_plan(cfg: RinthelConfig) -> Plan:
    shutdown = list(_shutdown_units(cfg))
    llama = services.LLAMA_SERVICE
    # llama-server tarda en soltar el puerto (mlock de un modelo grande): si
    # boot lo vuelve a prender, que lo encuentre libre. Solo si está
    # habilitado: si no, nadie lo mató ni nadie lo va a levantar.
    if llama.enabled_of(cfg):
        shutdown.append(
            Unit(
                llama.display_name.lower(),
                (
                    PhaseSpec(
                        f"◈ PUERTO {llama.wait_label} LIBRE",
                        managed_service.phase_wait_port_free,
                        {"port": llama.port_of(cfg)},
                    ),
                ),
            )
        )
    boot = (_docker_check_unit(), *[_local_unit(cfg, svc) for svc in _enabled_local(cfg)])
    rebuild = tuple(_docker_unit(cfg, svc, rebuild=True) for svc in _enabled_docker(cfg))
    return Plan(
        on_failure="stop",
        batches=(
            Batch(marker=None, units=tuple(shutdown)),
            Batch(marker="boot", units=boot),
            Batch(marker="rebuild", units=rebuild),
        ),
    )
