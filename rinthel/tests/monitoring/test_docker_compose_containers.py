"""Lo propio del adapter ``docker compose ps``: un ``ps`` por dir distinto de
``DOCKER_SERVICES`` (los cuatro viven en la raíz de la Instance), las dos
salidas de ``--format json`` según la versión, los puertos publicados, el
``cfg`` vivo y que un ``ps`` cancelado no queda corriendo."""

import asyncio
import dataclasses
import json
import os

import pytest

from rinthel_tui.monitoring.adapters.docker_compose import DockerComposeContainers
from rinthel_tui.monitoring.domain.types import DockerContainer

ROW = {"Name": "understory-1", "State": "running", "Status": "Up 1m", "Publishers": [
    {"PublishedPort": 3800, "TargetPort": 3800}, {"PublishedPort": 0, "TargetPort": 6334},
]}
UNDERSTORY = DockerContainer(name="understory-1", state="running", ports="3800->3800", status="Up 1m")


async def test_services_sharing_a_dir_run_one_ps(cfg, tmp_path, fake_executable):
    calls = tmp_path / "calls"
    fake_executable(tmp_path / "docker", (
        "import os, sys\n"
        f"open({str(calls)!r}, 'a').write(os.getcwd() + ' ' + ' '.join(sys.argv[1:]) + '\\n')\n"
        f"print({json.dumps(json.dumps(ROW))})\n"
    ))

    containers = await DockerComposeContainers(lambda: cfg, docker=str(tmp_path / "docker")).containers()

    assert containers == [UNDERSTORY]
    assert calls.read_text().splitlines() == [f"{cfg.instance.root} compose ps --format json"]


async def test_reads_a_json_array_as_well_as_json_lines(cfg, tmp_path, fake_executable):
    fake_executable(tmp_path / "docker", f"print({json.dumps(json.dumps([ROW, ROW]))})\n")

    containers = await DockerComposeContainers(lambda: cfg, docker=str(tmp_path / "docker")).containers()

    assert containers == [UNDERSTORY, UNDERSTORY]


async def test_each_read_uses_the_current_cfg(cfg, tmp_path, fake_executable):
    current = dataclasses.replace(cfg, instance=dataclasses.replace(cfg.instance, root=tmp_path / "no-existe"))
    fake_executable(tmp_path / "docker", f"print({json.dumps(json.dumps(ROW))})\n")
    status = DockerComposeContainers(lambda: current, docker=str(tmp_path / "docker"))

    assert await status.containers() == []  # ese dir no existe
    current = cfg
    assert await status.containers() == [UNDERSTORY]


async def test_a_failing_ps_is_an_empty_list(cfg, tmp_path, fake_executable):
    fake_executable(tmp_path / "docker", "import sys\nsys.exit(1)\n")

    assert await DockerComposeContainers(lambda: cfg, docker=str(tmp_path / "docker")).containers() == []


async def test_cancelled_ps_does_not_leave_docker_running(cfg, tmp_path, fake_executable):
    pid_file = tmp_path / "pid"
    fake_executable(tmp_path / "docker", (
        "import os, time\n"
        f"open({str(pid_file)!r}, 'w').write(str(os.getpid()))\n"
        "time.sleep(60)\n"
    ))
    task = asyncio.create_task(DockerComposeContainers(lambda: cfg, docker=str(tmp_path / "docker")).containers())
    while not pid_file.exists() or not pid_file.read_text():
        # Se conserva: espera un hecho del SO (el subproceso escribió su pid), sin
        # evento ni reloj del puerto que lo anuncie.
        await asyncio.sleep(0.01)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    with pytest.raises(ProcessLookupError):  # muerto y cosechado
        os.kill(int(pid_file.read_text()), 0)


async def test_ps_that_already_exited_still_propagates_the_cancellation(cfg):
    """La carrera entre cancelar y que el ``ps`` salga solo: ``kill`` levanta
    ``ProcessLookupError`` y la cancelación sigue igual."""

    class _AlreadyExited:
        returncode = None

        def __init__(self) -> None:
            self.started = asyncio.Event()

        async def communicate(self):
            self.started.set()
            await asyncio.Event().wait()

        def kill(self) -> None:
            raise ProcessLookupError

        async def wait(self) -> int:
            return 0

    ps = _AlreadyExited()

    async def fake_exec(*args, **kwargs):
        return ps

    task = asyncio.create_task(DockerComposeContainers(lambda: cfg, spawn=fake_exec).containers())
    await ps.started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
