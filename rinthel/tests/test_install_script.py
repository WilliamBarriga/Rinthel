"""``rinthel/install.sh`` run for real over a temporary copy, with every tool
it calls (Python, pip, cargo, ``rinthel-boot.sh``) replaced by a stub that
writes down how it was called. ``--voice`` (opt-in, repeatable) brings the
daemon up and asks it for INSTALL with the voice
(``python -m rinthel_tui.install --voice``, tested in ``test_install_cli.py``)
instead of opening the TUI."""

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

RINTHEL_DIR = Path(__file__).resolve().parents[1]

STUB = """#!/usr/bin/env bash
echo "{name} $*" >> "{log}"
exit {code}
"""


def _stub(path: Path, log: Path, name: str, code: int = 0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(STUB.format(name=name, log=log, code=code))
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


@pytest.fixture
def install(tmp_path):
    """A copy of ``install.sh`` in ``<root>/rinthel`` with stubs around it;
    returns a runner that answers ``(exit code, calls)``."""
    root = tmp_path / "instance"
    rinthel = root / "rinthel"
    (rinthel / "rinthel-client").mkdir(parents=True)
    shutil.copy(RINTHEL_DIR / "install.sh", rinthel / "install.sh")
    log = tmp_path / "calls.log"
    bin_dir = tmp_path / "bin"
    for tool in ("cargo", "cc", "curl"):
        _stub(bin_dir / tool, log, tool)
    _stub(bin_dir / "python3", log, "system-python")
    _stub(rinthel / ".venv" / "bin" / "python", log, "venv-python")
    _stub(rinthel / "rinthel-boot.sh", log, "boot")

    def run(*args: str, install_exit: int = 0) -> tuple[int, list[str]]:
        if install_exit:
            # The venv's Python answers INSTALL with this code; pip still succeeds.
            (rinthel / ".venv" / "bin" / "python").write_text(
                STUB.format(name="venv-python", log=log, code=0).replace(
                    "exit 0", f'[[ "$*" == *rinthel_tui.install* ]] && exit {install_exit}; exit 0'
                )
            )
        log.write_text("")
        env = {
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "HOME": str(tmp_path),
            "PYBIN": str(bin_dir / "python3"),
        }
        result = subprocess.run(["bash", str(rinthel / "install.sh"), *args], env=env, capture_output=True, text=True)
        return result.returncode, log.read_text().splitlines()

    run.root = root
    return run


def test_voice_brings_the_daemon_up_and_asks_for_install_with_voice(install):
    code, calls = install("--voice")

    assert code == 0
    assert calls[-2:] == [
        "boot --daemon-only",
        f"venv-python -m rinthel_tui.install --root {install.root} --voice",
    ]
    assert "cargo build --release --locked" in calls, "the bootstrap still runs first"


def test_voice_is_repeatable(install):
    first = install("--voice")
    second = install("--voice")

    assert first == second


def test_a_failed_voice_install_fails_the_script(install):
    code, calls = install("--voice", install_exit=1)

    assert code == 1
    assert calls[-1].startswith("venv-python -m rinthel_tui.install")


def test_without_voice_it_opens_the_tui_as_before(install):
    code, calls = install()

    assert code == 0
    assert calls[-1] == "boot "
    assert not any("rinthel_tui.install" in call for call in calls)


def test_skip_launch_still_stops_after_the_bootstrap(install):
    code, calls = install("--skip-launch")

    assert code == 0
    assert not any(call.startswith("boot") for call in calls)


def test_boot_has_a_daemon_only_mode_that_never_opens_the_client():
    script = (RINTHEL_DIR / "rinthel-boot.sh").read_text(encoding="utf-8")
    assert '"--daemon-only"' in script
    assert "(( DAEMON_ONLY )) && exit 0" in script
    assert script.index("(( DAEMON_ONLY )) && exit 0") < script.index('exec "$BINARY"')
