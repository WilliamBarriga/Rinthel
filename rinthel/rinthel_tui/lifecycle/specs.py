"""Lifecycle plans (see GLOSSARY.md): what each command runs — ordered
batches, DOCKER check included, and failure policy. ``executor.execute``
runs them.

BOOT/TERMINATE/RELOAD are built by iterating ``services.LOCAL_SERVICES``/
``services.DOCKER_SERVICES`` — adding or removing a service there (plus its
instance in ``services.py``) is enough for the plans to reflect it without
touching this file by hand.
"""

from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any, Literal

from rinthel_tui.config import RinthelConfig
from rinthel_tui.lifecycle import install, services
from rinthel_tui.lifecycle.domain.host import Host
from rinthel_tui.lifecycle.domain.outcome import PhaseReport
from rinthel_tui.lifecycle.domain.phases import data_dir, docker, service_phases
from rinthel_tui.lifecycle.service_defs import DockerComposeService, LocalProcessService

PhaseFn = Callable[..., Coroutine[Any, Any, None]]


@dataclass(frozen=True)
class PhaseSpec:
    """A plan phase: ``fn(host, report, **kwargs)``. What the phase needs
    (a service's spec, or the INSTALL task) arrives via ``kwargs``, already
    bound by the plan builder."""

    label: str
    fn: PhaseFn
    kwargs: dict[str, Any] = field(default_factory=dict)

    async def run(self, report: PhaseReport, host: Host) -> None:
        await self.fn(host, report, **self.kwargs)


@dataclass(frozen=True)
class Unit:
    """The phases of one unit — one ``ServiceOutcome`` in the response."""

    service: str
    phases: tuple[PhaseSpec, ...]


@dataclass(frozen=True)
class Batch:
    """A batch of units. ``marker`` is broadcast as ``phase_batch`` when it
    opens; ``None`` broadcasts nothing."""

    marker: str | None
    units: tuple[Unit, ...]


@dataclass(frozen=True)
class Plan:
    """Lifecycle plan: what a whole command runs. ``on_failure`` is the
    plan's failure policy — "stop" halts at the first failing unit,
    "continue" goes on with the remaining ones."""

    on_failure: Literal["stop", "continue"]
    batches: tuple[Batch, ...]


# ── per-service PhaseSpec builders — a single place that knows which label
# and which kwargs belong to each phase type ──────────────────────────────


def _spawn_spec(cfg: RinthelConfig, service: LocalProcessService) -> PhaseSpec:
    return PhaseSpec(f"◈ {service.menu_label}", service_phases.phase_spawn, {"service": service.spec(cfg)})


def _wait_spec(cfg: RinthelConfig, service: LocalProcessService | DockerComposeService) -> PhaseSpec:
    # Same phase_wait_ready for both service types — see
    # service_defs._ServiceBase, from which both inherit the ready/poll
    # fields.
    return PhaseSpec(f"◈ ESPERANDO {service.wait_label}", service_phases.phase_wait_ready, {"service": service.spec(cfg)})


def _kill_spec(cfg: RinthelConfig, service: LocalProcessService) -> PhaseSpec:
    return PhaseSpec(f"◈ {service.kill_label}", service_phases.phase_kill, {"service": service.spec(cfg)})


def _up_spec(cfg: RinthelConfig, service: DockerComposeService, *, rebuild: bool = False) -> PhaseSpec:
    return PhaseSpec(
        f"◈ {service.menu_label}",
        service_phases.phase_up,
        {"service": service.spec(cfg), "rebuild": rebuild},
    )


def _down_spec(cfg: RinthelConfig, service: DockerComposeService) -> PhaseSpec:
    return PhaseSpec(f"◈ {service.kill_label}", service_phases.phase_down, {"service": service.spec(cfg)})


# ── INSTALL ───────────────────────────────────────────────────────────────
# One Unit per enabled InstallUnit, plus PREFLIGHT as its own Unit and
# first: if CUDA/docker is missing there is no point going on with clone/
# build/download. Labels are not numbered: the daemon paints no checklist, it
# only needs what ran and whether it went well.
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
                f"◈ {unit.label}  --  SOLO LINUX", service_phases.phase_notice,
                {"message": "la voz es solo de Linux: INSTALL la omite en esta Platform"},
            )
            units.append(Unit(unit.label.lower(), (notice,)))
    return Plan(on_failure="stop", batches=(Batch(marker=None, units=tuple(units)),))


# ── BOOT/TERMINATE ────────────────────────────────────────────────────────
# One Unit per service: the daemon returns one ServiceOutcome per service in
# POST /boot and /terminate (wire shape fixed in docs/adr/0001), even though
# boot runs 2 phases per service (spawn+wait / up+wait) and terminate 1 (kill /
# down). The DOCKER check is one more Unit ("docker"), first in boot:
# if it fails, boot touches no service.


def _container_user(cfg: RinthelConfig) -> tuple[int, int]:
    """``PUID``/``PGID`` from the ``.env``, with the 1000:1000 compose uses if missing."""
    instance = cfg.instance
    return int(instance.variable("PUID") or 1000), int(instance.variable("PGID") or 1000)


def _enabled_local(cfg: RinthelConfig) -> list[LocalProcessService]:
    return [s for s in services.LOCAL_SERVICES if s.enabled_of(cfg)]


def _enabled_docker(cfg: RinthelConfig) -> list[DockerComposeService]:
    return [s for s in services.DOCKER_SERVICES if s.enabled_of(cfg)]


def _local_unit(cfg: RinthelConfig, svc: LocalProcessService) -> Unit:
    if svc is services.LLAMA_SERVICE and cfg.local_model is None:
        # Without a usable active Local model llama does not start: the notice
        # stays in the boot result and the rest of the services go on.
        notice = PhaseSpec(
            f"◈ {svc.menu_label}  --  SIN LOCAL MODEL ACTIVO",
            service_phases.phase_notice,
            {"message": cfg.model_warning or "sin Local model activo"},
        )
        return Unit(svc.display_name.lower(), (notice,))
    return Unit(svc.display_name.lower(), (_spawn_spec(cfg, svc), _wait_spec(cfg, svc)))


def restart_phases(cfg: RinthelConfig, service: LocalProcessService) -> tuple[PhaseSpec, ...]:
    """Stop whatever listens on ``service``'s port, launch it with ``cfg``'s
    model and wait for it to respond. Every step is required: a port that is
    not freed or a model that does not respond is a failure."""
    spec = service.spec(cfg)
    return (
        PhaseSpec(f"◈ {service.kill_label}", service_phases.phase_kill, {"service": spec, "required": True}),
        _spawn_spec(cfg, service),
        PhaseSpec(f"◈ ESPERANDO {service.wait_label}", service_phases.phase_wait_ready, {"service": spec, "required": True}),
    )


def restart_plan(cfg: RinthelConfig, service: LocalProcessService) -> Plan:
    """The Local model switch of the Capability ``service`` serves
    (``services.MODEL_SERVICES``): whoever switches decides the rollback."""
    unit = Unit(service.display_name.lower(), restart_phases(cfg, service))
    return Plan(on_failure="stop", batches=(Batch(marker=None, units=(unit,)),))


def stop_plan(cfg: RinthelConfig, service: LocalProcessService) -> Plan:
    """Turn a Capability off (``models off``): stop ``service`` by its
    port; a port that is not freed is a failure."""
    kill = PhaseSpec(f"◈ {service.kill_label}", service_phases.phase_kill, {"service": service.spec(cfg), "required": True})
    return Plan(on_failure="stop", batches=(Batch(marker=None, units=(Unit(service.display_name.lower(), (kill,)),)),))


def _docker_unit(cfg: RinthelConfig, svc: DockerComposeService, *, rebuild: bool = False) -> Unit:
    """A compose service: up and awaited. Deck, which runs as the host user,
    first of all hands its volume to the container's owner."""
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
    """Shared by ``terminate_plan`` and the shutdown of ``reload_plan``."""
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
    """``continue``: terminate goes on with what remains even if a service
    refuses to stop (GLOSSARY.md, Boot / Terminate)."""
    return Plan(on_failure="continue", batches=(Batch(marker=None, units=_shutdown_units(cfg)),))


# ── RELOAD ────────────────────────────────────────────────────────────────
# shutdown (no marker) → "boot" (DOCKER and the local services) →
# "rebuild" (docker, build + up). The markers travel as ``phase_batch``
# so the client knows when to fire its transitions (docs/adr/0001).
def reload_plan(cfg: RinthelConfig) -> Plan:
    shutdown = list(_shutdown_units(cfg))
    llama = services.LLAMA_SERVICE
    # llama-server is slow to release the port (mlock of a large model): if
    # boot turns it back on, it should find it free. Only if it is
    # enabled: otherwise nobody killed it and nobody will bring it up.
    if llama.enabled_of(cfg):
        shutdown.append(
            Unit(
                llama.display_name.lower(),
                (
                    PhaseSpec(
                        f"◈ PUERTO {llama.wait_label} LIBRE",
                        service_phases.phase_wait_port_free,
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
