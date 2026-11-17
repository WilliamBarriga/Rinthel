"""Starts, for the live suite, the model services that are missing.

It uses what the daemon uses: the ``argv``, ``env``, files and port of each
``LocalProcessService`` of ``lifecycle/services.py``. It never goes through
the Lifecycle's kill phase: killing by port would also take down the real
services of this machine, so the suite stops only the process group it
launched itself.
"""

from __future__ import annotations

import contextlib
import os
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Iterator, Sequence

from rinthel_tui.lifecycle.managed_service import LocalProcessService
from rinthel_tui.lifecycle.services import LLAMA_SERVICE


def _responds(url: str) -> bool:
    try:
        urllib.request.urlopen(url, timeout=2).read()
    except (urllib.error.URLError, OSError):
        return False
    return True


def _port_in_use(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def _spawn(service: LocalProcessService, cfg) -> subprocess.Popen:
    for directory in service.dirs_of(cfg):
        directory.mkdir(parents=True, exist_ok=True)
    for path, content in service.files_of(cfg).items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    log = service.log_of(cfg)
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("ab") as log_file:
        return subprocess.Popen(
            service.build_argv(cfg),
            env={**os.environ, **service.env_of(cfg)},
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )


def _wait_ready(service: LocalProcessService, cfg, proc: subprocess.Popen) -> None:
    deadline = time.monotonic() + service.default_ready_timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"{service.display_name} exited with {proc.returncode}: see {service.log_of(cfg)}")
        if _responds(service.ready_url_of(cfg)):
            return
        time.sleep(service.ready_poll_interval)
    raise RuntimeError(f"{service.display_name} did not answer within {service.default_ready_timeout}s")


def _stop(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()


@contextlib.contextmanager
def running_model_services(
    cfg, services: Sequence[LocalProcessService], *, allow_llm: bool = False
) -> Iterator[list[str]]:
    """Keeps ``services`` up while the block lasts and yields the names of
    the ones it started; on exit it stops only those. A port held by
    something that does not answer is an error, not something to kill.
    llama-server is started only with ``allow_llm`` (the explicit OK)."""
    started: list[tuple[LocalProcessService, subprocess.Popen]] = []
    try:
        for service in services:
            if _responds(service.ready_url_of(cfg)):
                continue
            if service.display_name == LLAMA_SERVICE.display_name and not allow_llm:
                raise RuntimeError(f"{service.display_name} is not answering and the suite does not start it on its own: pass --start-llm")
            if _port_in_use(service.port_of(cfg)):
                raise RuntimeError(f"{service.display_name}: :{service.port_of(cfg)} is busy and does not answer")
            proc = _spawn(service, cfg)
            started.append((service, proc))
            _wait_ready(service, cfg, proc)
        yield [service.display_name for service, _ in started]
    finally:
        for _, proc in reversed(started):
            _stop(proc)
