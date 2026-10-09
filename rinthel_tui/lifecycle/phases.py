"""Lo que no encaja en el patrón genérico de ``managed_service.py``: un
chequeo de infra (systemd/docker daemon) que no es ni un proceso local ni un
stack docker compose en sí mismo.

Todo lo que antes vivía acá — spawn/wait/kill de llama-server/whisper/tts,
up/down de Understory/Pithagoras — ahora es ``managed_service.phase_*``
parametrizado por un ``LocalProcessService``/``DockerComposeService`` de
``services.py``. Ver ``lifecycle/specs.py`` para cómo se arman las listas de
fases con eso.
"""

import asyncio
import os
import shutil

from rinthel_tui.config import RinthelConfig
from rinthel_tui.lifecycle.types import PhaseError, PhaseReport

_IS_WINDOWS = os.name == "nt"


async def _docker_daemon_is_ready() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "info",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except OSError:
        return False
    return await proc.wait() == 0

async def _systemctl_is_active(unit: str) -> bool:
    if shutil.which("systemctl") is None:
        return False
    proc = await asyncio.create_subprocess_exec(
        "systemctl", "is-active", "--quiet", unit,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    return await proc.wait() == 0


async def phase_check_docker(cfg: RinthelConfig, report: PhaseReport) -> None:
    if await _docker_daemon_is_ready():
        report.success("Docker daemon activo")
        return
    if _IS_WINDOWS:
        report.error(
            "DOCKER DAEMON INACTIVO — instala y abre Docker Desktop; "
            "espera a que indique que el motor está ejecutándose y vuelve a intentar"
        )
        raise PhaseError("docker daemon inactive; start Docker Desktop")
    # Intento de auto-levante no interactivo (`sudo -n`): si ya hay una regla
    # NOPASSWD para este comando, boot sigue solo; si no, `sudo` falla al
    # toque en vez de colgarse esperando una contraseña que nunca va a llegar
    # (este proceso no tiene TTY). Sin NOPASSWD configurado, el daemon nunca
    # levanta Docker solo — solo le pasa al usuario el comando exacto para
    # que lo corra a mano y el PRÓXIMO boot ya lo encuentre activo.
    try:
        proc = await asyncio.create_subprocess_exec(
            "sudo", "-n", "systemctl", "start", "docker",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except OSError:
        proc = None
    if proc is not None and await proc.wait() == 0 and await _docker_daemon_is_ready():
        report.success("Docker daemon estaba inactivo — levantado solo (sudo -n systemctl start docker)")
        return
    report.error(
        "DOCKER DAEMON INACTIVO — no hay sudo passwordless para levantarlo solo. "
        "Corré a mano: sudo systemctl start docker (el próximo boot ya arranca solo)"
    )
    raise PhaseError("docker daemon inactive, auto-start unavailable (no passwordless sudo)")
