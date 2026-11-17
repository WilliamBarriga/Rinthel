"""Suite de contrato del puerto ``Runner``: el subproceso real (asyncio) y el
``FakeRunner`` pasan lo mismo. Un comando que no existe no levanta: devuelve
rc 127 como el shell, con el motivo en la salida."""

from dataclasses import dataclass

import pytest

from rinthel_tui.lifecycle.adapters.asyncio_runner import AsyncioRunner
from rinthel_tui.lifecycle.adapters.windows_processes import WindowsRunner
from rinthel_tui.lifecycle.domain.types import RunResult
from tests.lifecycle.fakes import FakeRunner


@dataclass
class World:
    runner: object
    leave_file: object
    given: object  # (cmd, rc, output) -> None: el fake lo escribe en su guion; el real ya lo hace el comando


@pytest.fixture(params=["asyncio", "windows", "fake"])
def world(request):
    if request.param in ("asyncio", "windows"):
        # creationflags=0: the Windows flag does not exist on the Linux that runs the suite.
        runner = AsyncioRunner() if request.param == "asyncio" else WindowsRunner(creationflags=0)
        return World(runner, lambda path: None, lambda cmd, rc, output: None)
    fake = FakeRunner()
    return World(
        fake,
        lambda path: fake.on_failure("sh", lambda call: path.write_bytes(b"partial")),
        lambda cmd, rc, output: fake.script(cmd, rc=rc, output=output),
    )


async def test_a_command_returns_its_exit_code_and_combined_output(world):
    cmd = ["sh", "-c", "echo out; echo err >&2; exit 3"]
    world.given(cmd, 3, "out\nerr")

    result = await world.runner.run(cmd)

    assert result.rc == 3
    assert sorted(result.output.split()) == ["err", "out"]


async def test_a_successful_command_is_rc_zero(world):
    cmd = ["sh", "-c", "exit 0"]
    world.given(cmd, 0, "")

    assert await world.runner.run(cmd) == RunResult(rc=0, output="")


async def test_a_command_that_does_not_exist_is_rc_127_not_an_exception(world):
    result = await world.runner.run(["rinthel-no-such-binary-xyz"])

    assert result.rc == 127
    assert result.output != ""


async def test_a_failed_command_can_leave_partial_output_on_disk(world, tmp_path):
    target = tmp_path / "model.part"
    cmd = ["sh", "-c", 'printf partial > "$1"; exit 18', "download", str(target)]
    world.given(cmd, 18, "")
    world.leave_file(target)

    result = await world.runner.run(cmd)

    assert result.rc == 18
    assert target.read_bytes() == b"partial"


async def test_a_command_without_execute_permission_is_an_error_result(world, tmp_path):
    executable = tmp_path / "non-executable-nvcc"
    executable.write_text("#!/bin/sh\nexit 0\n")
    cmd = [str(executable), "--version"]
    world.given(cmd, 127, "Permission denied")

    result = await world.runner.run(cmd)

    assert result.rc == 127
    assert "Permission denied" in result.output
