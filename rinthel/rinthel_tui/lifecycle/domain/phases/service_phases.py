"""Las phases genéricas de un servicio gestionado — spawn/wait/kill de un
proceso local y up/down/recreate de un servicio ``docker compose`` —, una
sola vez para todos los servicios en vez de una función casi idéntica por
servicio.

Cada una respeta la firma ``(host, report, **kwargs)`` que exige ``PhaseSpec``
(``lifecycle/specs.py``): el ``Host`` (ADR 0004) trae los puertos del host
donde corre la Instance, y el ``service`` — un ``LocalProcessSpec`` o un
``DockerComposeSpec`` ya armado a partir de la config — viaja por ``kwargs``.
Ninguna lee ``RinthelConfig``: las definiciones de ``services.py`` la
convierten en spec antes de armar el plan."""

from pathlib import Path

from rinthel_tui.lifecycle.domain.errors import PhaseError, SpawnFailed
from rinthel_tui.lifecycle.domain.host import Host
from rinthel_tui.lifecycle.domain.outcome import PhaseReport, fail_on_error, report_output, require_ok
from rinthel_tui.lifecycle.domain.types import DockerComposeSpec, LocalProcessSpec, ServiceSpec

_MAX_LOG_BYTES = 10 * 1024 * 1024  # 10MB — arriba de esto, rotamos antes de escribir más
# Cuánto se espera tras lanzar un proceso para decir que no murió al instante.
_SPAWN_GRACE_SECONDS = 1.5
# Cuánto se espera a que un puerto se libere tras el SIGTERM antes del SIGKILL.
_TERM_GRACE_SECONDS = 10


def _rotate_log_if_large(log: Path, max_bytes: int = _MAX_LOG_BYTES) -> None:
    """Rota ``log`` a ``log.1`` (un solo backup) si ya pasó ``max_bytes`` —
    sin esto, un log de un proceso de larga vida (llama-server corriendo
    semanas) crece sin límite. Se llama en cada ``phase_spawn``, así que
    cubre cada BOOT/RELOAD; no protege dentro de una misma corrida larga sin
    reinicio, para eso hace falta logrotate a nivel de sistema."""
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
    """Poll de ``url`` con backoff exponencial (capeado en ``max_interval``)
    hasta que responda 200 o se agote ``timeout``. Arranca en ``interval``
    para no perder la respuesta rápida de servicios livianos (tts) y crece
    para no saturar el endpoint de un servicio que tarda en cargar (modelos
    grandes en llama-server) con polls cada 2s durante 90s. Devuelve True si
    llegó a responder."""
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
    """El puerto con el que se habla del servicio. Un servicio sin puerto no
    es direccionable: que una fase que sí lo necesita llegue
    acá es un error de programación, no una condición operativa."""
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
    # Sin esto, un binario/flag roto que crashea al instante queda reportado
    # como "lanzado" y la fase siguiente solo se entera 90s después con un
    # timeout genérico.
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
    """Poll de ``service.ready_url`` — compartido entre los servicios locales y
    los de docker compose. Un servicio sin ``ready_url`` (sin healthcheck HTTP
    propio) no tiene nada que pollear y vuelve al toque. Devuelve si
    respondió: para boot un timeout es solo un aviso, para quien lo necesite
    arriba (``phase_recreate_with_new_secret``) es un fallo. Con ``required``
    el timeout es un fallo de la fase."""
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
    """Con ``required``, un puerto que sigue ocupado después de forzar es un
    fallo de la fase, no un aviso."""
    # Matamos por puerto (no por PID guardado): lo que importa es quién sea
    # que esté escuchando ahí.
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
    """Una unidad que no corre: deja su motivo como aviso en el resultado."""
    report.warn(message)


async def phase_wait_port_free(host: Host, report: PhaseReport, *, port: int, timeout: int = 30) -> None:
    """Genérico a propósito (no atado a un servicio): RELOAD lo usa para
    esperar a que el puerto de un servicio puntual (hoy llama-server) quede
    libre entre el shutdown y el boot."""
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
    """Un ``--build-arg`` por cada ``npm_build_args``, con la última versión
    publicada del paquete (``latest`` si el registry no responde)."""
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
    # El nombre del servicio es obligatorio (el adapter siempre lo nombra): sin él compose
    # recrea todo el proyecto con el env de este servicio solamente.
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
    # Solo este servicio: los servicios compose comparten un mismo compose
    # project (docker-compose.yaml en la raíz, ver services.py) — un `down` a
    # secas tumbaría los otros también.
    result = await host.compose.down(service.stack)
    require_ok(
        report, result, failed=f"{service.display_name}: docker compose down falló",
        error=f"{service.display_name.lower()} down failed",
    )
    report.success(f"{service.display_name} parado")
