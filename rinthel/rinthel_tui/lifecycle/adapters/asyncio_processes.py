import asyncio
import contextlib
import os
import signal
from collections.abc import Mapping, Sequence
from pathlib import Path

import psutil

from rinthel_tui.lifecycle.domain.errors import SpawnFailed
from rinthel_tui.lifecycle.domain.types import ProcessHandle


class AsyncioProcesses:
    """``Processes`` POSIX sobre asyncio y señales: cada proceso en su propia
    sesión (equivale a nohup + disown), así que su pid es también el de su
    grupo y una señal le llega a lo que lance. Quién escucha en un puerto lo
    dice psutil, sin depender de ``fuser``."""

    def __init__(self) -> None:
        self._procs: dict[int, asyncio.subprocess.Process] = {}

    async def spawn(
        self, argv: Sequence[str], *, log: Path, cwd: Path | None = None, env: Mapping[str, str] | None = None
    ) -> ProcessHandle:
        # El hijo hereda su propio fd: cerrar el nuestro apenas arrancó no le corta el log.
        with await asyncio.to_thread(open, log, "ab") as log_file:
            try:
                proc = await asyncio.create_subprocess_exec(
                    *argv,
                    cwd=str(cwd) if cwd else None,
                    env={**os.environ, **env} if env else None,
                    stdout=log_file,
                    stderr=asyncio.subprocess.STDOUT,
                    start_new_session=True,
                )
            except OSError as exc:
                raise SpawnFailed(f"{argv[0]}: {exc.strerror or exc}") from exc
        self._procs[proc.pid] = proc
        return ProcessHandle(proc.pid)

    def is_alive(self, handle: ProcessHandle) -> bool:
        pid = handle.pid
        proc = self._procs.get(pid)
        if proc is not None:
            return proc.returncode is None
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def terminate(self, handle: ProcessHandle) -> None:
        self._signal(handle, signal.SIGTERM)

    def kill(self, handle: ProcessHandle) -> None:
        self._signal(handle, signal.SIGKILL)

    def _signal(self, handle: ProcessHandle, sig: signal.Signals) -> None:
        if not self.is_alive(handle):
            return
        with contextlib.suppress(ProcessLookupError):
            os.killpg(handle.pid, sig)

    async def stop_listeners(self, port: int, *, force: bool = False) -> list[int]:
        return await asyncio.to_thread(_signal_listeners, port, force)


def _signal_listeners(port: int, force: bool) -> list[int]:
    try:
        connections = psutil.net_connections(kind="tcp")
    except (OSError, psutil.Error):
        return []
    pids = {
        conn.pid
        for conn in connections
        if conn.pid and conn.status == psutil.CONN_LISTEN and conn.laddr and conn.laddr.port == port
    }
    signalled: list[int] = []
    for pid in sorted(pids):
        try:
            process = psutil.Process(pid)
            process.kill() if force else process.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        signalled.append(pid)
    return signalled
