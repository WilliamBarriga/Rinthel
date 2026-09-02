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
    log_file = open(cfg.log, "ab")
    try:
        proc = await asyncio.create_subprocess_exec(
            str(cfg.bin), "-m", str(cfg.model),
            "-ngl", "all", "-c", "131072", "-fa", "on", "-fit", "off",
            "--port", str(cfg.port),
            "--n-cpu-moe", "60", "--threads-batch", "7", "--threads", "8",
            "--ubatch-size", "512", "--batch-size", "512", "--parallel", "1",
            "--temp", "0.7", "--top-p", "0.8", "--top-k", "20", "--min-p", "0.1",
            "--repeat-penalty", "1.05",
            "--cache-reuse", "256", "--cache-ram", "-1", "--load-mode", "mlock",
            "--spec-type", "draft-mtp", "--spec-draft-n-max", "2",
            stdout=log_file,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,  # equivalente a nohup + disown
        )
    finally:
        log_file.close()
    report.success(f"llama-server lanzado en background (PID {proc.pid}) — log: {cfg.log}")


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
    proc = await asyncio.create_subprocess_exec(
        "pkill", "-f", f"llama-server.*--port {cfg.port}",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    rc = await proc.wait()
    if rc == 0:
        report.success(f"llama-server parado en :{cfg.port}")
    else:
        report.warn(f"No había llama-server corriendo en :{cfg.port}")


# ── UNDERSTORY / PITHAGORAS (shutdown) ───────────────────────


async def _stop_service(directory: Path, label: str, report: PhaseReport) -> None:
    if not directory.is_dir():
        report.warn(f"{directory} no encontrado — omitido")
        return
    await _docker_compose(["down"], directory, report)
    report.success(f"{label} parado")


async def phase_stop_understory(cfg: RinthelConfig, report: PhaseReport) -> None:
    await _stop_service(cfg.understory_dir, "Understory", report)


async def phase_stop_pithagoras(cfg: RinthelConfig, report: PhaseReport) -> None:
    await _stop_service(cfg.pithagoras_dir, "Pithagoras", report)


async def phase_wait_port_free(cfg: RinthelConfig, report: PhaseReport, port: int | None = None) -> None:
    target = port if port is not None else cfg.port
    while await _port_in_use(target):
        await asyncio.sleep(1)


# ── UNDERSTORY / PITHAGORAS (boot) ────────────────────────────


async def phase_up_understory(cfg: RinthelConfig, report: PhaseReport) -> None:
    if not cfg.understory_dir.is_dir():
        report.warn(f"{cfg.understory_dir} no encontrado — omitido")
        return
    await _docker_compose(["up", "-d"], cfg.understory_dir, report)
    await _docker_compose(["logs", "--tail", "5", "understory"], cfg.understory_dir, report)


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
        await _docker_compose(["build", "--no-cache", "portal"], cfg.pithagoras_dir, report, extra_env)
    await _docker_compose(["up", "-d"], cfg.pithagoras_dir, report, extra_env)
    await _docker_compose(["logs", "--tail", "5", "portal"], cfg.pithagoras_dir, report, extra_env)
