"""Motor genérico de "servicio gestionado" — reemplaza el spawn/wait/kill
triplicado (llama-server, whisper, tts) y el up/down duplicado (Understory,
Pithagoras) que antes vivían como funciones ``phase_*`` casi idénticas por
servicio en ``phases.py``.

``LocalProcessService`` describe un binario local (puerto, log, cómo armar
su ``argv`` a partir de ``cfg``); ``DockerComposeService`` describe un stack
``docker compose``. Las instancias concretas (LLAMA_SERVICE, etc.) viven en
``services.py``, construidas a partir de los sub-configs de ``config.py``.

Todas las fases genéricas de acá respetan la firma ``(cfg, report, **kwargs)``
que exige ``PhaseSpec`` (``lifecycle/specs.py``) — cada ``PhaseSpec`` pasa el
``service`` correspondiente por ``kwargs`` en vez de haber una función
distinta por servicio.
"""

import asyncio
import os
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from rinthel_tui.config import RinthelConfig
from rinthel_tui.lifecycle.types import PhaseError, PhaseReport

# ── helpers de subprocess/red — sin cambios de comportamiento respecto a
# los que vivían en phases.py, solo mudados acá ──────────────────────────


async def _run(
    cmd: Sequence[str],
    report: PhaseReport,
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> int:
    """Corre un comando, reporta stdout+stderr combinados, devuelve el returncode."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    out, _ = await proc.communicate()
    text = out.decode(errors="replace").rstrip()
    if text:
        report.info(text)
    return proc.returncode


async def _docker_compose(
    args: Sequence[str],
    cwd: Path,
    report: PhaseReport,
    extra_env: dict[str, str] | None = None,
) -> int:
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    return await _run(["docker", "compose", *args], report, cwd=cwd, env=env)


async def _port_in_use(port: int) -> bool:
    def _check() -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(("127.0.0.1", port)) == 0

    return await asyncio.to_thread(_check)


async def _http_ok(url: str, timeout: float = 2.0) -> bool:
    import urllib.request

    def _check() -> bool:
        try:
            with urllib.request.urlopen(url, timeout=timeout):
                return True
        except OSError:
            return False

    return await asyncio.to_thread(_check)


_MAX_LOG_BYTES = 10 * 1024 * 1024  # 10MB — arriba de esto, rotamos antes de escribir más


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
    while not await _http_ok(url):
        if waited >= timeout:
            return False
        sleep_for = min(interval, timeout - waited)
        await asyncio.sleep(sleep_for)
        waited += sleep_for
        interval = min(interval * backoff, max_interval)
    return True


# ── campos compartidos por LocalProcessService y DockerComposeService ────
#
# Ambos tipos de servicio se esperan igual (wait_ready pollea ready_url_of
# con el mismo backoff) y se listan igual en menú/report, así que ese
# subconjunto de campos vive acá una sola vez — evita mantenerlo duplicado
# entre las dos dataclasses y permite que phase_wait_ready (más abajo) sea
# una sola función en vez de una por tipo de servicio.
# kw_only=True porque las subclases suman sus propios campos requeridos
# (build_argv/log_of, dir_of/compose_service_name) después de los que ya
# tienen default acá — sin kw_only, un dataclass no lo permite.


@dataclass(frozen=True, kw_only=True)
class _ServiceBase:
    # display_name: usado en los mensajes de report ("llama-server murió al
    # instante", "no relanzo whisper-server"). menu_label/wait_label/
    # kill_label: texto de los PhaseSpec en specs.py — separados de
    # display_name porque no siempre coinciden (ej. "TTS — PIPER" en el menú
    # vs. "tts-piper" en los mensajes).
    display_name: str
    menu_label: str
    wait_label: str
    kill_label: str
    port_of: Callable[[RinthelConfig], int]
    # Filtra el servicio de INSTALL/BOOT/DOWN/RELOAD cuando da False (ver
    # ``specs.py`` a partir de Fase 3) — default True porque hoy los 5
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


# ── LocalProcessService: llama-server / whisper / tts ────────────────────


@dataclass(frozen=True, kw_only=True)
class LocalProcessService(_ServiceBase):
    build_argv: Callable[[RinthelConfig], list[str]]
    log_of: Callable[[RinthelConfig], Path]


async def phase_spawn(cfg: RinthelConfig, report: PhaseReport, *, service: LocalProcessService) -> None:
    port = service.port_of(cfg)
    if await _port_in_use(port):
        report.warn(f"Ya hay algo escuchando en :{port} — no relanzo {service.display_name}")
        return
    log = service.log_of(cfg)
    log.parent.mkdir(parents=True, exist_ok=True)
    _rotate_log_if_large(log)
    log_file = open(log, "ab")
    argv = service.build_argv(cfg)
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=log_file,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,  # equivalente a nohup + disown
        )
    finally:
        log_file.close()
    # Sin esto, un binario/flag roto que crashea al instante queda reportado
    # como "lanzado" y la fase siguiente solo se entera 90s después con un
    # timeout genérico.
    try:
        rc = await asyncio.wait_for(proc.wait(), timeout=1.5)
    except asyncio.TimeoutError:
        report.success(f"{service.display_name} lanzado en background (PID {proc.pid}) — log: {log}")
    else:
        report.error(f"{service.display_name} murió al instante (rc {rc}) — revisa {log}")
        raise PhaseError(f"{service.display_name} exited immediately (rc {rc})")


async def check_ready(cfg: RinthelConfig, service: _ServiceBase) -> bool:
    """Chequeo puntual de ``service.ready_url_of`` — un solo GET, sin el
    backoff/retry de ``phase_wait_ready`` ni un ``PhaseReport`` para
    escribirle. Pensado para telemetría en vivo fuera de una fase de boot/
    reload (ver ``daemon.py::llama_status_task``): ahí lo que importa es el
    estado actual en cada tick, no esperar a que aparezca."""
    if service.ready_url_of is None:
        return False
    return await _http_ok(service.ready_url_of(cfg))


async def phase_wait_ready(
    cfg: RinthelConfig, report: PhaseReport, *, service: _ServiceBase, timeout: int | None = None
) -> None:
    """Poll de ``service.ready_url_of`` — compartido entre LocalProcessService
    y DockerComposeService (ambos son ``_ServiceBase``, con los mismos campos
    de ready/poll). Antes eran dos funciones casi idénticas; la única
    diferencia real era este guard de ``ready_url_of is None``, que en un
    LocalProcessService nunca dispara (siempre define uno)."""
    if service.ready_url_of is None:
        return
    timeout = service.default_ready_timeout if timeout is None else timeout
    ready = await _wait_http_ready(
        service.ready_url_of(cfg),
        timeout=timeout,
        interval=service.ready_poll_interval,
        max_interval=service.ready_poll_max_interval,
        backoff=service.ready_poll_backoff,
    )
    if not ready:
        report.warn(f"AVISO: nada respondiendo en :{service.port_of(cfg)} tras {timeout}s")
        if service.on_timeout_hint:
            report.info(service.on_timeout_hint)
        return
    report.success(f"{service.display_name} respondiendo en :{service.port_of(cfg)}")


async def phase_kill(cfg: RinthelConfig, report: PhaseReport, *, service: LocalProcessService) -> None:
    # Matamos por puerto (no por PID guardado) — mismo criterio que el
    # código original: lo que importa es quién sea que esté escuchando ahí.
    port = service.port_of(cfg)
    if not await _port_in_use(port):
        report.warn(f"No había {service.display_name} corriendo en :{port}")
        return
    await _run(["fuser", "-k", "-TERM", f"{port}/tcp"], report)
    for _ in range(10):
        if not await _port_in_use(port):
            report.success(f"{service.display_name} parado en :{port}")
            return
        await asyncio.sleep(1)
    await _run(["fuser", "-k", "-KILL", f"{port}/tcp"], report)
    if await _port_in_use(port):
        report.warn(f"AVISO: :{port} sigue ocupado tras intentar matar el proceso")
    else:
        report.success(f"{service.display_name} parado en :{port} (SIGKILL)")


async def phase_wait_port_free(
    cfg: RinthelConfig, report: PhaseReport, *, port_of: Callable[[RinthelConfig], int], timeout: int = 30
) -> None:
    """Genérico a propósito (no atado a ``LocalProcessService`` ni a un
    puerto fijo): RELOAD lo usa para esperar a que el puerto de un servicio
    puntual (hoy llama-server) quede libre entre el shutdown y el boot."""
    port = port_of(cfg)
    waited = 0
    while await _port_in_use(port):
        if waited >= timeout:
            report.warn(f"AVISO: :{port} sigue ocupado tras {timeout}s — continuando de todos modos")
            return
        await asyncio.sleep(1)
        waited += 1
    report.success(f"Puerto :{port} libre")


# ── DockerComposeService: Understory / Pithagoras ────────────────────────


@dataclass(frozen=True, kw_only=True)
class DockerComposeService(_ServiceBase):
    dir_of: Callable[[RinthelConfig], Path]
    compose_service_name: str
    extra_env_of: Callable[[RinthelConfig], dict[str, str]] = lambda cfg: {}
    # Solo Pithagoras rebuildea la imagen del frontend antes de levantar.
    build_args: tuple[str, ...] | None = None
    # Los stacks docker tardan menos en levantar que llama-server cargando
    # un modelo grande — pisa el default de 90s de _ServiceBase.
    default_ready_timeout: int = 60


async def phase_up(
    cfg: RinthelConfig, report: PhaseReport, *, service: DockerComposeService, no_cache: bool = False
) -> None:
    directory = service.dir_of(cfg)
    if not directory.is_dir():
        report.warn(f"{directory} no encontrado — omitido")
        return
    extra_env = service.extra_env_of(cfg)
    if no_cache and service.build_args:
        report.warn(f"Reconstruyendo imagen {service.display_name.lower()}…")
        rc = await _docker_compose(list(service.build_args), directory, report, extra_env)
        if rc != 0:
            report.error(f"{service.display_name}: docker compose build falló (rc {rc})")
            raise PhaseError(f"{service.display_name.lower()} build failed (rc {rc})")
    rc = await _docker_compose(["up", "-d"], directory, report, extra_env)
    await _docker_compose(["logs", "--tail", "5", service.compose_service_name], directory, report, extra_env)
    if rc != 0:
        report.error(f"{service.display_name}: docker compose up falló (rc {rc})")
        raise PhaseError(f"{service.display_name.lower()} up failed (rc {rc})")
    report.success(f"{service.display_name} levantado")


async def phase_down(cfg: RinthelConfig, report: PhaseReport, *, service: DockerComposeService) -> None:
    directory = service.dir_of(cfg)
    if not directory.is_dir():
        report.warn(f"{directory} no encontrado — omitido")
        return
    rc = await _docker_compose(["down"], directory, report)
    if rc != 0:
        report.error(f"{service.display_name}: docker compose down falló (rc {rc})")
        raise PhaseError(f"{service.display_name.lower()} down failed (rc {rc})")
    report.success(f"{service.display_name} parado")
