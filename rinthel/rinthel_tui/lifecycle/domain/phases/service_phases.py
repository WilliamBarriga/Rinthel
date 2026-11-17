"""The generic phases of a managed service — spawn/wait/kill of a local
process and up/down/recreate of a ``docker compose`` service —, written once
for all services instead of a near-identical function per service.

Each one follows the ``(host, report, **kwargs)`` signature that
``PhaseSpec`` requires (``lifecycle/specs.py``): the ``Host``
(ports-and-adapters ADR) carries the ports of the host where the Instance
runs, and the ``service`` — a ``LocalProcessSpec`` or a
``DockerComposeSpec`` already built from the config — travels via
``kwargs``. None reads ``RinthelConfig``: the ``services.py`` definitions
turn it into a spec before building the plan."""

from pathlib import Path

from rinthel_tui.lifecycle.domain.errors import PhaseError, SpawnFailed
from rinthel_tui.lifecycle.domain.host import Host
from rinthel_tui.lifecycle.domain.outcome import PhaseReport, fail_on_error, report_output, require_ok
from rinthel_tui.lifecycle.domain.types import DockerComposeSpec, LocalProcessSpec, ServiceSpec

_MAX_LOG_BYTES = 10 * 1024 * 1024  # 10MB — above this, rotate before writing more
# How long to wait after launching a process before saying it did not die instantly.
_SPAWN_GRACE_SECONDS = 1.5
# How long to wait for a port to be freed after SIGTERM before SIGKILL.
_TERM_GRACE_SECONDS = 10


def _rotate_log_if_large(log: Path, max_bytes: int = _MAX_LOG_BYTES) -> None:
    """Rotate ``log`` to ``log.1`` (a single backup) once it exceeds
    ``max_bytes`` — without this, the log of a long-lived process
    (llama-server running for weeks) grows without bound. Called on every
    ``phase_spawn``, so it covers each BOOT/RELOAD; it does not protect within
    a single long run without restart, that needs system-level logrotate."""
    if log.exists() and log.stat().st_size > max_bytes:
        rotated = log.with_name(log.name + ".1")
        rotated.unlink(missing_ok=True)
        log.rename(rotated)


async def _wait_http_ready(
    host: Host,
    url: str,
    *,
    timeout: float,
    interval: float,
    max_interval: float,
    backoff: float,
) -> bool:
    """Poll ``url`` with exponential backoff (capped at ``max_interval``)
    until it answers 200 or ``timeout`` runs out. Starts at ``interval`` so
    as not to miss the quick answer of lightweight services (tts) and grows
    so as not to flood the endpoint of a slow-loading service (large models
    in llama-server) with polls every 2s for 90s. Return True if it
    answered."""
    waited = 0.0
    while not await host.probe.http_ok(url):
        if waited >= timeout:
            return False
        sleep_for = min(interval, timeout - waited)
        await host.clock.sleep(sleep_for)
        waited += sleep_for
        interval = min(interval * backoff, max_interval)
    return True


def service_port(service: ServiceSpec) -> int:
    """The port used to talk to the service. A service without a port is not
    addressable: a phase that does need one reaching
    here is a programming error, not an operational condition."""
    if service.port is None:
        raise ValueError(f"{service.display_name} has no port to talk to")
    return service.port


# ── LocalProcessSpec: llama-server ──────────────────────────────────────


async def phase_spawn(host: Host, report: PhaseReport, *, service: LocalProcessSpec) -> None:
    port = service_port(service)
    if await host.probe.port_open(port):
        report.warn(f"Ya hay algo escuchando en :{port} — no relanzo {service.display_name}")
        return
    for directory in service.dirs:
        directory.mkdir(parents=True, exist_ok=True)
    for path, content in service.files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    service.log.parent.mkdir(parents=True, exist_ok=True)
    _rotate_log_if_large(service.log)
    try:
        process = await host.processes.spawn(service.argv, log=service.log, env=service.env or None)
    except SpawnFailed as exc:
        report.error(f"{service.display_name} no arrancó: {exc}")
        raise PhaseError(f"{service.display_name} failed to start: {exc}") from exc
    # Without this, a broken binary/flag that crashes instantly is reported
    # as "launched" and the next phase only finds out 90s later with a
    # generic timeout.
    await host.clock.sleep(_SPAWN_GRACE_SECONDS)
    if not host.processes.is_alive(process):
        report.error(f"{service.display_name} murió al instante — revisa {service.log}")
        raise PhaseError(f"{service.display_name} exited immediately")
    report.success(f"{service.display_name} lanzado en background (PID {process.pid}) — log: {service.log}")


async def phase_wait_ready(
    host: Host,
    report: PhaseReport,
    *,
    service: ServiceSpec,
    timeout: int | None = None,
    required: bool = False,
) -> bool:
    """Poll ``service.ready_url`` — shared between local and docker compose
    services. A service without ``ready_url`` (no HTTP healthcheck of its
    own) has nothing to poll and returns right away. Return whether it
    answered: for boot a timeout is only a warning, for whoever needs it
    up (``phase_recreate_with_new_secret``) it is a failure. With
    ``required`` the timeout is a phase failure."""
    if service.ready_url is None:
        return True
    timeout = service.ready_timeout if timeout is None else timeout
    ready = await _wait_http_ready(
        host,
        service.ready_url,
        timeout=timeout,
        interval=service.ready_poll_interval,
        max_interval=service.ready_poll_max_interval,
        backoff=service.ready_poll_backoff,
    )
    if not ready:
        report.warn(f"AVISO: nada respondiendo en :{service_port(service)} tras {timeout}s")
        if service.on_timeout_hint:
            report.info(service.on_timeout_hint)
        if required:
            report.error(f"{service.display_name} no respondió en :{service_port(service)}")
            raise PhaseError(f"{service.display_name} not ready after {timeout}s")
        return False
    report.success(f"{service.display_name} respondiendo en :{service_port(service)}")
    return True


async def phase_kill(host: Host, report: PhaseReport, *, service: ServiceSpec, required: bool = False) -> None:
    """With ``required``, a port still busy after forcing is a phase
    failure, not a warning."""
    # Kill by port (not by a stored PID): what matters is whoever is
    # listening there.
    port = service_port(service)
    if not await host.probe.port_open(port):
        report.warn(f"No había {service.display_name} corriendo en :{port}")
        return
    if not await host.processes.stop_listeners(port):
        report.warn(f"No pude identificar el proceso que escucha en :{port}")
    for _ in range(_TERM_GRACE_SECONDS):
        if not await host.probe.port_open(port):
            report.success(f"{service.display_name} parado en :{port}")
            return
        await host.clock.sleep(1)
    await host.processes.stop_listeners(port, force=True)
    if await host.probe.port_open(port):
        if required:
            report.error(f"{service.display_name}: :{port} sigue ocupado tras forzar la terminación")
            raise PhaseError(f"{service.display_name} port {port} still busy after forced termination")
        report.warn(f"AVISO: :{port} sigue ocupado tras intentar matar el proceso")
    else:
        report.success(f"{service.display_name} parado en :{port} (terminación forzada)")


async def phase_notice(host: Host, report: PhaseReport, *, message: str) -> None:
    """A unit that does not run: leaves its reason as a warning in the result."""
    report.warn(message)


async def phase_wait_port_free(host: Host, report: PhaseReport, *, port: int, timeout: int = 30) -> None:
    """Generic on purpose (not tied to a service): RELOAD uses it to wait
    for the port of a specific service (today llama-server) to be free
    between shutdown and boot."""
    waited = 0
    while await host.probe.port_open(port):
        if waited >= timeout:
            report.warn(f"AVISO: :{port} sigue ocupado tras {timeout}s — continuando de todos modos")
            return
        await host.clock.sleep(1)
        waited += 1
    report.success(f"Puerto :{port} libre")


# ── DockerComposeSpec: Understory / portal ────────────────────────────


async def _build_args(host: Host, service: DockerComposeSpec, report: PhaseReport) -> dict[str, str]:
    """One ``--build-arg`` per ``npm_build_args`` entry, with the package's
    latest published version (``latest`` if the registry does not answer)."""
    build: dict[str, str] = {}
    for arg, package in service.npm_build_args:
        version = await host.registry.latest(package)
        if version is None:
            report.warn(f"No se pudo consultar la última versión de {package} — {arg}=latest (capa desde el cache)")
            version = "latest"
        build[arg] = version
    return build


async def phase_up(host: Host, report: PhaseReport, *, service: DockerComposeSpec, rebuild: bool = False) -> None:
    directory = service.stack.directory
    if not directory.is_dir():
        report.warn(f"{directory} no encontrado — omitido")
        return
    build = None
    if rebuild and service.build_args:
        report.warn(f"Reconstruyendo imagen {service.display_name.lower()}…")
        build = await _build_args(host, service, report)
    # The service name is mandatory (the adapter always names it): without it compose
    # recreates the whole project with only this service's env.
    result = await host.compose.up(service.stack, build=build)
    report_output(report, result)
    report_output(report, await host.compose.logs(service.stack, tail=5))
    fail_on_error(
        report, result, failed=f"{service.display_name}: docker compose up falló",
        error=f"{service.display_name.lower()} up failed",
    )
    report.success(f"{service.display_name} levantado")


async def phase_down(host: Host, report: PhaseReport, *, service: DockerComposeSpec) -> None:
    directory = service.stack.directory
    if not directory.is_dir():
        report.warn(f"{directory} no encontrado — omitido")
        return
    # Only this service: the compose services share one compose project
    # (docker-compose.yaml at the root, see services.py) — a bare `down`
    # would take the others down too.
    result = await host.compose.down(service.stack)
    require_ok(
        report, result, failed=f"{service.display_name}: docker compose down falló",
        error=f"{service.display_name.lower()} down failed",
    )
    report.success(f"{service.display_name} parado")
