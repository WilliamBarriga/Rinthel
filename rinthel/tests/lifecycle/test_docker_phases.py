"""``domain/phases/docker.py``, what does not fit the service_phases.py
pattern: the Docker daemon check. The rest (service spawn/wait/kill, docker
up/down) is tested in test_service_phases.py. Runs against a ``Host`` of
doubles."""

import pytest

from rinthel_tui.lifecycle.domain.errors import PhaseError
from rinthel_tui.lifecycle.domain.phases import docker as phases
from tests.lifecycle.fakes import fake_host

INFO = ["docker", "info"]
START = ["sudo", "-n", "systemctl", "start", "docker"]


async def test_check_docker_succeeds_when_the_daemon_answers(report):
    host, _ = fake_host()
    host.runner.script(INFO, rc=0)

    await phases.phase_check_docker(host, report)

    assert len(report.successes) == 1 and report.errors == []
    assert [call.cmd for call in host.runner.calls] == [tuple(INFO)]  # no intentó levantarlo


async def test_check_docker_starts_an_inactive_daemon_with_passwordless_sudo(report):
    host, log = fake_host()
    host.runner.script_rcs(INFO, [1, 0])  # down, then up after starting it
    host.runner.script(START, rc=0)

    await phases.phase_check_docker(host, report)

    assert report.errors == [] and len(report.successes) == 1
    assert [event[1] for event in log if event[0] == "run"] == [tuple(INFO), tuple(START), tuple(INFO)]


@pytest.mark.parametrize("start_rc", [1, 0], ids=["sudo-needs-a-password", "start-did-not-take"])
async def test_check_docker_fails_the_phase_telling_the_admin_what_to_run(report, start_rc):
    host, _ = fake_host()
    host.runner.script(INFO, rc=1)
    host.runner.script(START, rc=start_rc)

    with pytest.raises(PhaseError):
        await phases.phase_check_docker(host, report)

    assert len(report.errors) == 1 and report.successes == []


async def test_check_docker_on_windows_points_at_docker_desktop_without_sudo(report):
    host, _ = fake_host()
    host.host_info.os = "windows"
    host.runner.script(INFO, rc=1)

    with pytest.raises(PhaseError):
        await phases.phase_check_docker(host, report)

    assert "Docker Desktop" in report.errors[0]
    assert not host.runner.ran("sudo")
