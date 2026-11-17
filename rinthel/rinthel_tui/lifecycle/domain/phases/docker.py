"""Lo que no encaja en el patrón genérico de ``managed_service.py``: un
chequeo de infra (el daemon de Docker) que no es ni un proceso local ni un
stack docker compose en sí mismo."""

from rinthel_tui.lifecycle.domain.errors import PhaseError
from rinthel_tui.lifecycle.domain.host import Host
from rinthel_tui.lifecycle.domain.outcome import PhaseReport


async def _docker_ready(host: Host) -> bool:
    return (await host.runner.run(["docker", "info"])).rc == 0


async def phase_check_docker(host: Host, report: PhaseReport) -> None:
    if await _docker_ready(host):
        report.success("Docker daemon activo")
        return
    if host.host_info.platform() == "windows":
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
    started = await host.runner.run(["sudo", "-n", "systemctl", "start", "docker"])
    if started.rc == 0 and await _docker_ready(host):
        report.success("Docker daemon estaba inactivo — levantado solo (sudo -n systemctl start docker)")
        return
    report.error(
        "DOCKER DAEMON INACTIVO — no hay sudo passwordless para levantarlo solo. "
        "Corré a mano: sudo systemctl start docker (el próximo boot ya arranca solo)"
    )
    raise PhaseError("docker daemon inactive, auto-start unavailable (no passwordless sudo)")
