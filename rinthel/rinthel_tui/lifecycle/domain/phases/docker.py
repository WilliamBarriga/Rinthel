"""What does not fit the generic pattern of ``service_phases.py``: an infra
check (the Docker daemon) that is neither a local process nor a docker
compose stack itself."""

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
    # Non-interactive auto-start attempt (`sudo -n`): if there is already a
    # NOPASSWD rule for this command, boot carries on by itself; if not,
    # `sudo` fails right away instead of hanging on a password that will never
    # come (this process has no TTY). Without NOPASSWD configured, the daemon
    # never starts Docker by itself — it only hands the user the exact command
    # to run by hand so the NEXT boot finds it already running.
    started = await host.runner.run(["sudo", "-n", "systemctl", "start", "docker"])
    if started.rc == 0 and await _docker_ready(host):
        report.success("Docker daemon estaba inactivo — levantado solo (sudo -n systemctl start docker)")
        return
    report.error(
        "DOCKER DAEMON INACTIVO — no hay sudo passwordless para levantarlo solo. "
        "Corré a mano: sudo systemctl start docker (el próximo boot ya arranca solo)"
    )
    raise PhaseError("docker daemon inactive, auto-start unavailable (no passwordless sudo)")
