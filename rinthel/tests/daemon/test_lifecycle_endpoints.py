"""POST /boot, /terminate, /reload, /install — por HTTP, con
Lifecycle reemplazado por ``get_lifecycle``: acá auth y forma de la
respuesta, incluido el error de configure generado por el executor con
Host falso. Qué corre cada comando y cuándo corta vive en
tests/lifecycle/test_specs.py y test_executor.py."""

import pytest

from rinthel_tui.api.deps import get_lifecycle
from rinthel_tui.lifecycle import executor, install, install_tasks
from rinthel_tui.lifecycle.commands import Lifecycle
from rinthel_tui.lifecycle.domain.errors import PhaseError
from rinthel_tui.lifecycle.domain.types import UnitOutcome
from rinthel_tui.lifecycle.specs import Batch, PhaseSpec, Plan, Unit
from tests.lifecycle.fakes import fake_host

COMMANDS = ["boot", "terminate", "reload", "install"]


class FakeLifecycle:
    def __getattr__(self, command: str):
        async def run() -> list[UnitOutcome]:
            return [UnitOutcome(service=command, ok=True, message="hecho")]

        return run


@pytest.fixture(autouse=True)
def _fake_lifecycle(app):
    app.dependency_overrides[get_lifecycle] = FakeLifecycle


@pytest.mark.parametrize("command", COMMANDS)
def test_lifecycle_command_returns_the_outcomes_of_its_run(client, service_headers, command):
    response = client.post(f"/{command}", headers=service_headers)

    assert response.status_code == 200
    assert response.json() == {"results": [{"service": command, "ok": True, "message": "hecho"}]}


@pytest.mark.parametrize("command", COMMANDS)
def test_lifecycle_command_rejects_a_caller_without_the_service_secret(client, command):
    assert client.post(f"/{command}").status_code == 401


def test_a_phase_error_is_a_failed_unit_in_the_install_http_response(app, client, service_headers):
    async def failing_phase(host, report):
        report.error("download failed")
        raise PhaseError("download failed")

    async def broadcast(type_, data):
        pass

    class FailingInstall:
        async def install(self):
            plan = Plan("stop", (Batch(None, (Unit("model", (PhaseSpec("download", failing_phase),)),)),))
            return await executor.execute(plan, broadcast, fake_host()[0])

    app.dependency_overrides[get_lifecycle] = FailingInstall
    response = client.post("/install", headers=service_headers)

    assert response.status_code == 200
    assert response.json() == {"results": [{"service": "model", "ok": False, "message": "download failed"}]}


def test_install_returns_the_configure_failure_as_a_service_outcome(app, client, service_headers, tmp_path):
    host, _ = fake_host()
    host.host_info.install_cuda("/usr/local/cuda-12.8/bin/nvcc")
    host.runner.script_program("cmake", rc=2, output="configure failed")
    task = install_tasks.LlamaCppInstall(tmp_path / "llama.cpp", "https://example.test/llama.cpp", "master")
    plan = Plan(on_failure="stop", batches=(Batch(marker=None, units=(
        Unit("llama.cpp + modelo", (
            PhaseSpec("build CUDA", install.phase_install_build_llamacpp, {"task": task}),
        )),
    )),))

    class BuildLifecycle:
        async def install(self) -> list[UnitOutcome]:
            return await executor.execute(plan, app.state.broadcaster.broadcast, host)

    app.dependency_overrides[get_lifecycle] = BuildLifecycle
    response = client.post("/install", headers=service_headers)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"results"}
    outcome, = body["results"]
    assert set(outcome) == {"service", "ok", "message"}
    assert outcome["service"] == "llama.cpp + modelo" and outcome["ok"] is False
    assert "cmake configure falló (rc 2)" in outcome["message"]
    assert len(host.runner.ran("cmake")) == 1


@pytest.mark.parametrize("tool,rc,hint", [("nvidia-smi", 9, "driver NVIDIA"), ("nvcc", 127, "CUDA toolkit")])
def test_install_reports_gpu_execution_failure_before_provisioning(
    app, client, service_headers, daemon_cfg, tool, rc, hint,
):
    host, _ = fake_host()
    host.runner.succeed_by_default()
    for name in ("git", "curl", "cmake", "nvidia-smi", "nvcc"):
        host.host_info.install(name, f"/tools/{name}")
    host.runner.script_program(f"/tools/{tool}", rc=rc, output="broken tool")

    async def broadcast(type_, data):
        pass

    lifecycle = Lifecycle(daemon_cfg, broadcast, execute=executor.bound_to(host))
    app.dependency_overrides[get_lifecycle] = lambda: lifecycle

    response = client.post("/install", headers=service_headers)

    assert response.status_code == 200
    result, = response.json()["results"]
    assert result["service"] == "preflight"
    assert result["ok"] is False
    assert tool in result["message"] and f"rc {rc}" in result["message"]
    assert hint in result["message"]
    assert not host.runner.ran("systemctl")
    assert not host.runner.ran("sudo")
    assert host.compose.calls == []
    assert host.processes.spawns == []
