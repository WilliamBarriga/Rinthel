"""Lógica de negocio pura — misma fuente para cualquier pantalla que la use.

Reemplaza ``nightcity/framework/rinthel-phases.sh``. Cada ``phase_*`` es
async, recibe ``cfg`` (RinthelConfig) y ``report`` (PhaseReport) explícitos
— nada de variables de entorno leídas a ciegas ni de asumir en qué subshell
corre — y levanta ``PhaseError`` en vez de ``exit 1`` cuando la fase no
puede continuar. ``lifecycle/runner.py`` decide qué hacer con eso.
"""

import asyncio
import os
import socket
import sys
from pathlib import Path
from typing import Protocol, Sequence

from rinthel_tui.config import RinthelConfig


class PhaseError(Exception):
    """Fallo esperado de una fase (equivalente al `exit 1` de bash)."""


class PhaseReport(Protocol):
    def info(self, msg: str) -> None: ...
    def success(self, msg: str) -> None: ...
    def warn(self, msg: str) -> None: ...
    def error(self, msg: str) -> None: ...


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


# ── LLAMA-SERVER ─────────────────────────────────────────────


async def phase_check_docker(cfg: RinthelConfig, report: PhaseReport) -> None:
    proc = await asyncio.create_subprocess_exec(
        "systemctl", "is-active", "--quiet", "docker",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    rc = await proc.wait()
    if rc != 0:
        report.error("DOCKER DAEMON INACTIVO")
        report.info("Ejecuta primero: sudo systemctl start docker")
        raise PhaseError("docker daemon inactive")
    report.success("Docker daemon activo")


# --load-mode mlock reemplaza al --no-mmap --mlock viejo (deprecados, y en
# conflicto con --load-mode none de otros perfiles: el binario solo respeta
# el último flag de carga en la línea de comandos, que ya era --mlock).
async def phase_spawn_llama_server(cfg: RinthelConfig, report: PhaseReport) -> None:
    if await _port_in_use(cfg.port):
        report.warn(f"Ya hay algo escuchando en :{cfg.port} — no relanzo llama-server")
        return
    log_file = open(cfg.log, "ab")
    argv = [
        str(cfg.bin), "-m", str(cfg.model),
        "-ngl", cfg.ngl,
        "-c", str(cfg.context_window),
        "-fa", "on" if cfg.flash_attention else "off",
        "-fit", "on" if cfg.flash_inference else "off",
        "--port", str(cfg.port),
        "--n-cpu-moe", str(cfg.n_cpu_moe),
        "--threads-batch", str(cfg.threads_batch),
        "--threads", str(cfg.threads),
        "--ubatch-size", str(cfg.ubatch_size),
        "--batch-size", str(cfg.batch_size),
        "--parallel", str(cfg.parallel),
        "--temp", str(cfg.temperature),
        "--top-p", str(cfg.top_p),
        "--top-k", str(cfg.top_k),
        "--min-p", str(cfg.min_p),
        "--repeat-penalty", str(cfg.repeat_penalty),
        "--cache-reuse", str(cfg.cache_reuse),
        "--cache-ram", str(cfg.cache_ram),
        "--load-mode", cfg.load_mode,
        "--spec-type", cfg.spec_type,
        "--spec-draft-n-max", str(cfg.spec_draft_n_max),
    ]
    if cfg.moe_cache_slots > 0:
        argv += ["--moe-cache-profile", str(cfg.moe_cache_profile), "--moe-cache-slots", str(cfg.moe_cache_slots)]
    if not cfg.sched_async_cpu:
        argv += ["--no-sched-async-cpu"]
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=log_file,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,  # equivalente a nohup + disown
        )
    finally:
        log_file.close()
    # Sin esto, un binario/flag roto que crashea al instante (ej. un typo en
    # un flag: pasó de verdad) queda reportado como "lanzado" — y la fase
    # siguiente solo se entera 90s después con un timeout genérico.
    try:
        rc = await asyncio.wait_for(proc.wait(), timeout=1.5)
    except asyncio.TimeoutError:
        report.success(f"llama-server lanzado en background (PID {proc.pid}) — log: {cfg.log}")
    else:
        report.error(f"llama-server murió al instante (rc {rc}) — revisa {cfg.log}")
        raise PhaseError(f"llama-server exited immediately (rc {rc})")


async def phase_wait_llama_ready(cfg: RinthelConfig, report: PhaseReport, timeout: int = 90) -> None:
    url = f"http://127.0.0.1:{cfg.port}/v1/models"
    waited = 0
    while not await _http_ok(url):
        if waited >= timeout:
            report.warn(f"AVISO: nada respondiendo en :{cfg.port} tras {timeout}s")
            report.info("Levanta el modelo local antes de usar understory.")
            return
        await asyncio.sleep(2)
        waited += 2
    report.success(f"llama-server respondiendo en :{cfg.port}")


async def phase_kill_llama_server(cfg: RinthelConfig, report: PhaseReport) -> None:
    # `pkill -f` matcheaba contra la línea de comandos exacta con la que
    # phase_spawn_llama_server lanza el proceso — cualquier llama-server
    # levantado a mano o por una versión vieja del script (flags distintos)
    # no matcheaba y el phase reportaba "no había nada" con el server bien
    # arriba. Detectamos/matamos por el puerto (mismo chequeo que
    # phase_wait_llama_ready/phase_wait_port_free), que es lo que de verdad
    # nos importa: quién sea que esté escuchando en :cfg.port.
    if not await _port_in_use(cfg.port):
        report.warn(f"No había llama-server corriendo en :{cfg.port}")
        return
    await _run(["fuser", "-k", "-TERM", f"{cfg.port}/tcp"], report)
    for _ in range(10):
        if not await _port_in_use(cfg.port):
            report.success(f"llama-server parado en :{cfg.port}")
            return
        await asyncio.sleep(1)
    await _run(["fuser", "-k", "-KILL", f"{cfg.port}/tcp"], report)
    if await _port_in_use(cfg.port):
        report.warn(f"AVISO: :{cfg.port} sigue ocupado tras intentar matar el proceso")
    else:
        report.success(f"llama-server parado en :{cfg.port} (SIGKILL)")


# ── WHISPER (STT, CPU-only) ──────────────────────────────────


async def phase_spawn_whisper_server(cfg: RinthelConfig, report: PhaseReport) -> None:
    if await _port_in_use(cfg.whisper_port):
        report.warn(f"Ya hay algo escuchando en :{cfg.whisper_port} — no relanzo whisper-server")
        return
    cfg.whisper_log.parent.mkdir(parents=True, exist_ok=True)
    log_file = open(cfg.whisper_log, "ab")
    argv = [
        str(cfg.whisper_bin),
        "--host", "127.0.0.1",
        "--port", str(cfg.whisper_port),
        "-m", str(cfg.whisper_model),
        "-t", str(cfg.whisper_threads),
        "-l", "auto",
        # El browser graba en audio/webm;codecs=opus — el decoder interno de
        # whisper.cpp no lo entiende ("failed to decode audio data").
        # --convert shellea a ffmpeg (debe estar en PATH del host) para pasar
        # cualquier formato a WAV 16kHz antes de transcribir.
        "--convert",
        "--tmp-dir", str(cfg.whisper_log.parent),
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=log_file,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,  # equivalente a nohup + disown
        )
    finally:
        log_file.close()
    try:
        rc = await asyncio.wait_for(proc.wait(), timeout=1.5)
    except asyncio.TimeoutError:
        report.success(f"whisper-server lanzado en background (PID {proc.pid}) — log: {cfg.whisper_log}")
    else:
        report.error(f"whisper-server murió al instante (rc {rc}) — revisa {cfg.whisper_log}")
        raise PhaseError(f"whisper-server exited immediately (rc {rc})")


async def phase_wait_whisper_ready(cfg: RinthelConfig, report: PhaseReport, timeout: int = 90) -> None:
    url = f"http://127.0.0.1:{cfg.whisper_port}/"
    waited = 0
    while not await _http_ok(url):
        if waited >= timeout:
            report.warn(f"AVISO: nada respondiendo en :{cfg.whisper_port} tras {timeout}s")
            return
        await asyncio.sleep(2)
        waited += 2
    report.success(f"whisper-server respondiendo en :{cfg.whisper_port}")


async def phase_kill_whisper_server(cfg: RinthelConfig, report: PhaseReport) -> None:
    if not await _port_in_use(cfg.whisper_port):
        report.warn(f"No había whisper-server corriendo en :{cfg.whisper_port}")
        return
    await _run(["fuser", "-k", "-TERM", f"{cfg.whisper_port}/tcp"], report)
    for _ in range(10):
        if not await _port_in_use(cfg.whisper_port):
            report.success(f"whisper-server parado en :{cfg.whisper_port}")
            return
        await asyncio.sleep(1)
    await _run(["fuser", "-k", "-KILL", f"{cfg.whisper_port}/tcp"], report)
    if await _port_in_use(cfg.whisper_port):
        report.warn(f"AVISO: :{cfg.whisper_port} sigue ocupado tras intentar matar el proceso")
    else:
        report.success(f"whisper-server parado en :{cfg.whisper_port} (SIGKILL)")


# ── TTS (Piper, CPU-only) ─────────────────────────────────────


async def phase_spawn_tts_server(cfg: RinthelConfig, report: PhaseReport) -> None:
    if await _port_in_use(cfg.tts_port):
        report.warn(f"Ya hay algo escuchando en :{cfg.tts_port} — no relanzo tts-piper")
        return
    cfg.tts_log.parent.mkdir(parents=True, exist_ok=True)
    log_file = open(cfg.tts_log, "ab")
    argv = [
        sys.executable, str(cfg.tts_server_script),
        "--host", "127.0.0.1",
        "--port", str(cfg.tts_port),
        "--piper-bin", str(cfg.tts_bin),
        "--voice-es", str(cfg.tts_voice_es),
        "--voice-en", str(cfg.tts_voice_en),
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=log_file,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,  # equivalente a nohup + disown
        )
    finally:
        log_file.close()
    try:
        rc = await asyncio.wait_for(proc.wait(), timeout=1.5)
    except asyncio.TimeoutError:
        report.success(f"tts-piper lanzado en background (PID {proc.pid}) — log: {cfg.tts_log}")
    else:
        report.error(f"tts-piper murió al instante (rc {rc}) — revisa {cfg.tts_log}")
        raise PhaseError(f"tts-piper exited immediately (rc {rc})")


async def phase_wait_tts_ready(cfg: RinthelConfig, report: PhaseReport, timeout: int = 30) -> None:
    url = f"http://127.0.0.1:{cfg.tts_port}/"
    waited = 0
    while not await _http_ok(url):
        if waited >= timeout:
            report.warn(f"AVISO: nada respondiendo en :{cfg.tts_port} tras {timeout}s")
            return
        await asyncio.sleep(1)
        waited += 1
    report.success(f"tts-piper respondiendo en :{cfg.tts_port}")


async def phase_kill_tts_server(cfg: RinthelConfig, report: PhaseReport) -> None:
    if not await _port_in_use(cfg.tts_port):
        report.warn(f"No había tts-piper corriendo en :{cfg.tts_port}")
        return
    await _run(["fuser", "-k", "-TERM", f"{cfg.tts_port}/tcp"], report)
    for _ in range(10):
        if not await _port_in_use(cfg.tts_port):
            report.success(f"tts-piper parado en :{cfg.tts_port}")
            return
        await asyncio.sleep(1)
    await _run(["fuser", "-k", "-KILL", f"{cfg.tts_port}/tcp"], report)
    if await _port_in_use(cfg.tts_port):
        report.warn(f"AVISO: :{cfg.tts_port} sigue ocupado tras intentar matar el proceso")
    else:
        report.success(f"tts-piper parado en :{cfg.tts_port} (SIGKILL)")


# ── UNDERSTORY / PITHAGORAS (shutdown) ───────────────────────


async def _stop_service(directory: Path, label: str, report: PhaseReport) -> None:
    if not directory.is_dir():
        report.warn(f"{directory} no encontrado — omitido")
        return
    rc = await _docker_compose(["down"], directory, report)
    if rc != 0:
        report.error(f"{label}: docker compose down falló (rc {rc})")
        raise PhaseError(f"{label} down failed (rc {rc})")
    report.success(f"{label} parado")


async def phase_stop_understory(cfg: RinthelConfig, report: PhaseReport) -> None:
    await _stop_service(cfg.understory_dir, "Understory", report)


async def phase_stop_pithagoras(cfg: RinthelConfig, report: PhaseReport) -> None:
    await _stop_service(cfg.pithagoras_dir, "Pithagoras", report)


async def phase_wait_port_free(
    cfg: RinthelConfig, report: PhaseReport, port: int | None = None, timeout: int = 30
) -> None:
    target = port if port is not None else cfg.port
    waited = 0
    while await _port_in_use(target):
        if waited >= timeout:
            report.warn(f"AVISO: :{target} sigue ocupado tras {timeout}s — continuando de todos modos")
            return
        await asyncio.sleep(1)
        waited += 1
    report.success(f"Puerto :{target} libre")


# ── UNDERSTORY / PITHAGORAS (boot) ────────────────────────────


async def phase_up_understory(cfg: RinthelConfig, report: PhaseReport) -> None:
    if not cfg.understory_dir.is_dir():
        report.warn(f"{cfg.understory_dir} no encontrado — omitido")
        return
    rc = await _docker_compose(["up", "-d"], cfg.understory_dir, report)
    await _docker_compose(["logs", "--tail", "5", "understory"], cfg.understory_dir, report)
    if rc != 0:
        report.error(f"Understory: docker compose up falló (rc {rc})")
        raise PhaseError(f"understory up failed (rc {rc})")
    report.success("Understory levantado")


# Sin --no-cache: levanta con la imagen actual (ruta rápida, execute).
# Con --no-cache: reconstruye la imagen del frontend antes de levantar
# (reload) — el Dockerfile compila web/ -> web/dist y sin rebuild queda
# el build anterior.
async def phase_build_up_pithagoras(cfg: RinthelConfig, report: PhaseReport, no_cache: bool = False) -> None:
    if not cfg.pithagoras_dir.is_dir():
        report.warn(f"{cfg.pithagoras_dir} no encontrado — omitido")
        return
    extra_env = {"PORT": str(cfg.pithagoras_port)}
    if no_cache:
        report.warn("Reconstruyendo imagen pithagoras…")
        rc = await _docker_compose(["build", "--no-cache", "portal"], cfg.pithagoras_dir, report, extra_env)
        if rc != 0:
            report.error(f"Pithagoras: docker compose build falló (rc {rc})")
            raise PhaseError(f"pithagoras build failed (rc {rc})")
    rc = await _docker_compose(["up", "-d"], cfg.pithagoras_dir, report, extra_env)
    await _docker_compose(["logs", "--tail", "5", "portal"], cfg.pithagoras_dir, report, extra_env)
    if rc != 0:
        report.error(f"Pithagoras: docker compose up falló (rc {rc})")
        raise PhaseError(f"pithagoras up failed (rc {rc})")
    report.success("Pithagoras levantado")
