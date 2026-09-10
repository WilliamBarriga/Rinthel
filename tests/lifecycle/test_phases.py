"""Lo único que queda en phases.py tras el split a managed_service.py: el
chequeo de systemd/docker daemon. El resto (spawn/wait/kill de servicios,
up/down docker) se prueba en test_managed_service.py, parametrizado por
service en vez de por función.
"""

import asyncio

from rinthel_tui.lifecycle import phases
from rinthel_tui.lifecycle.types import PhaseError


async def test_check_docker_succeeds_when_daemon_active(monkeypatch, cfg, report):
    async def fake_exec(*args, **kwargs):
        class _Proc:
            async def wait(self):
                return 0

        return _Proc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    await phases.phase_check_docker(cfg, report)

    assert any("Docker daemon activo" in msg for msg in report.successes)


async def test_check_docker_raises_when_daemon_inactive(monkeypatch, cfg, report):
    async def fake_exec(*args, **kwargs):
        class _Proc:
            async def wait(self):
                return 1

        return _Proc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    try:
        await phases.phase_check_docker(cfg, report)
        raised = False
    except PhaseError:
        raised = True

    assert raised
    assert any("DOCKER DAEMON INACTIVO" in msg for msg in report.errors)
