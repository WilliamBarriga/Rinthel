"""Windows adapters of ``Runner`` and ``Processes``. They reuse the asyncio
adapters and change only what differs on Windows: children get their own
process group through ``creationflags`` instead of a POSIX session, and
stopping a process stops its whole tree through psutil (there is no
``killpg``, and ``os.kill`` would call ``TerminateProcess`` on any signal).

``creationflags`` is the only thing that varies: the default is the Windows
value; a host that is not Windows (the contract suites on Linux) passes 0."""

import asyncio
from typing import Any

import psutil

from rinthel_tui.lifecycle.adapters.asyncio_processes import AsyncioProcesses
from rinthel_tui.lifecycle.adapters.asyncio_runner import AsyncioRunner
from rinthel_tui.lifecycle.domain.types import ProcessHandle

# subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW; spelled out
# because the subprocess constants only exist on Windows.
WINDOWS_CREATIONFLAGS = 0x00000200 | 0x08000000


def _stop_tree(pid: int, *, force: bool) -> None:
    try:
        root = psutil.Process(pid)
        tree = [*root.children(recursive=True), root]
    except psutil.NoSuchProcess:
        return
    for process in tree:
        try:
            process.kill() if force else process.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue


class WindowsRunner(AsyncioRunner):
    def __init__(self, *, creationflags: int = WINDOWS_CREATIONFLAGS) -> None:
        self._creationflags = creationflags

    def _isolation(self) -> dict[str, Any]:
        return {"creationflags": self._creationflags}

    def _kill_owned(self, proc: asyncio.subprocess.Process) -> None:
        _stop_tree(proc.pid, force=True)


class WindowsProcesses(AsyncioProcesses):
    def __init__(self, *, creationflags: int = WINDOWS_CREATIONFLAGS) -> None:
        super().__init__()
        self._creationflags = creationflags

    def _isolation(self) -> dict[str, Any]:
        return {"creationflags": self._creationflags}

    def is_alive(self, handle: ProcessHandle) -> bool:
        proc = self._procs.get(handle.pid)
        if proc is not None:
            return proc.returncode is None
        try:
            return psutil.Process(handle.pid).status() != psutil.STATUS_ZOMBIE
        except psutil.NoSuchProcess:
            return False
        except psutil.AccessDenied:
            return True

    def terminate(self, handle: ProcessHandle) -> None:
        if self.is_alive(handle):
            _stop_tree(handle.pid, force=False)

    def kill(self, handle: ProcessHandle) -> None:
        if self.is_alive(handle):
            _stop_tree(handle.pid, force=True)
