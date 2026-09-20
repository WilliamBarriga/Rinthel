"""Lo único que queda en phases.py tras el split a managed_service.py: el
chequeo de systemd/docker daemon. El resto (spawn/wait/kill de servicios,
up/down docker) se prueba en test_managed_service.py, parametrizado por
service en vez de por función.
"""

from rinthel_tui.lifecycle import phases
from rinthel_tui.lifecycle.types import PhaseError


async def test_check_docker_succeeds_when_daemon_active(monkeypatch, cfg, report):
    async def ready():
        return True

    monkeypatch.setattr(phases, "_docker_daemon_is_ready", ready)

    await phases.phase_check_docker(cfg, report)

    assert any("Docker daemon activo" in msg for msg in report.successes)


async def test_check_docker_raises_when_daemon_inactive(monkeypatch, cfg, report):
    async def not_ready():
        return False

    monkeypatch.setattr(phases, "_docker_daemon_is_ready", not_ready)
    monkeypatch.setattr(phases, "_IS_WINDOWS", True)

    try:
        await phases.phase_check_docker(cfg, report)
        raised = False
    except PhaseError:
        raised = True

    assert raised
    assert any("Docker Desktop" in msg for msg in report.errors)


async def test_check_docker_auto_starts_with_passwordless_sudo(monkeypatch, cfg, report):
    """Docker inactivo + `sudo -n systemctl start docker` disponible: el
    daemon lo levanta solo en vez de solo avisar."""
    import asyncio

    calls: list[tuple[str, ...]] = []
    checks = iter([False, True])

    async def docker_ready():
        return next(checks)

    async def fake_exec(*args, **kwargs):
        calls.append(args)

        class _Proc:
            async def wait(self):
                return 0

        return _Proc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(phases, "_docker_daemon_is_ready", docker_ready)
    monkeypatch.setattr(phases, "_IS_WINDOWS", False)

    await phases.phase_check_docker(cfg, report)

    assert not report.errors
    assert any("levantado solo" in msg for msg in report.successes)
    assert ("sudo", "-n", "systemctl", "start", "docker") in calls


async def test_check_docker_reports_actionable_command_without_passwordless_sudo(monkeypatch, cfg, report):
    import asyncio

    async def not_ready():
        return False

    async def fake_exec(*args, **kwargs):
        class _Proc:
            async def wait(self):
                return 1  # nunca activo, sudo -n tampoco anda

        return _Proc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(phases, "_docker_daemon_is_ready", not_ready)
    monkeypatch.setattr(phases, "_IS_WINDOWS", False)

    try:
        await phases.phase_check_docker(cfg, report)
    except PhaseError:
        pass

    assert any("sudo systemctl start docker" in msg for msg in report.errors)
