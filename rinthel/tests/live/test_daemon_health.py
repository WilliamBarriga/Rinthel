"""Health of the real daemon: what used to be checked by hand with ``pgrep``
and ``grep Traceback``. Each test starts its own daemon with ``spawn_daemon``
to look at its child processes without mixing them with the real stack's.
That ``daemon.log`` has no ``Traceback`` is demanded of every test daemon
when it stops (``_running_daemon``)."""

import json
import signal
import subprocess
import time

from websockets.sync.client import connect

MONITOR_OPENS = 5
DOCKER_STATUS_TIMEOUT_S = 15


def _open_monitor_until_docker_status(daemon) -> None:
    with connect(daemon.ws_monitor_url) as ws:
        deadline = time.monotonic() + DOCKER_STATUS_TIMEOUT_S
        while time.monotonic() < deadline:
            if json.loads(ws.recv(timeout=DOCKER_STATUS_TIMEOUT_S))["type"] == "docker_status":
                return
    raise AssertionError("the Monitor did not send docker_status")


def _compose_ps_children(pid: int) -> list[str]:
    result = subprocess.run(
        ["pgrep", "-af", "-P", str(pid), "docker compose ps"], capture_output=True, text=True, check=False
    )
    return result.stdout.splitlines()


def test_opening_and_closing_the_monitor_leaves_no_docker_compose_ps_behind(spawn_daemon):
    daemon = spawn_daemon()

    for _ in range(MONITOR_OPENS):
        _open_monitor_until_docker_status(daemon)

    # With nobody connected the Monitor stops reading docker: a `ps` still
    # alive would be an orphan of a connection that is already closed.
    time.sleep(2)
    assert _compose_ps_children(daemon.pid) == []


def test_a_ctrl_c_shutdown_is_clean(spawn_daemon):
    daemon = spawn_daemon()
    _open_monitor_until_docker_status(daemon)

    daemon.stop()

    # uvicorn re-raises the signal that stopped it after closing the
    # lifespan: 0 or -SIGINT is a clean close; -SIGKILL means it had to be killed.
    assert daemon.proc.returncode in (0, -signal.SIGINT), daemon.log
    assert "Task was destroyed but it is pending" not in daemon.log
