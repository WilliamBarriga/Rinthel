"""Lo que solo el ``AsyncioRunner`` real puede garantizar y un doble no imita:
el directorio de trabajo y cómo se mezcla el entorno."""

from rinthel_tui.lifecycle.adapters.asyncio_runner import AsyncioRunner


async def test_the_command_runs_in_the_given_directory(tmp_path):
    result = await AsyncioRunner().run(["pwd"], cwd=tmp_path)

    assert result.output == str(tmp_path.resolve())


async def test_env_is_a_delta_over_the_base_environment(monkeypatch):
    monkeypatch.setenv("RINTHEL_BASE_VAR", "base")

    result = await AsyncioRunner().run(
        ["sh", "-c", 'echo "$RINTHEL_BASE_VAR $RINTHEL_DELTA_VAR"'], env={"RINTHEL_DELTA_VAR": "delta"}
    )

    assert result.output == "base delta"


async def test_cancelling_a_command_reaps_its_process(tmp_path):
    import asyncio
    import os
    import signal
    import sys

    import pytest

    pidfile = tmp_path / "pid"
    script = "import os,pathlib,time; pathlib.Path(__import__('sys').argv[1]).write_text(str(os.getpid())); time.sleep(30)"
    command = asyncio.create_task(AsyncioRunner().run([sys.executable, "-c", script, str(pidfile)]))
    try:
        async with asyncio.timeout(5):
            while not pidfile.exists():
                await asyncio.sleep(0.01)
        pid = int(pidfile.read_text())
        command.cancel()
        with pytest.raises(asyncio.CancelledError):
            await command
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
    finally:
        command.cancel()
        if pidfile.exists():
            try:
                os.kill(int(pidfile.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass
