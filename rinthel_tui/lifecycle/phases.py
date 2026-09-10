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

from rinthel_tui.config import RinthelConfig
from rinthel_tui.lifecycle.types import PhaseError, PhaseReport


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
