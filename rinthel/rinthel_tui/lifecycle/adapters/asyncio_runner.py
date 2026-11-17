import asyncio
import os
import signal
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from rinthel_tui.lifecycle.domain.types import RunResult


class AsyncioRunner:
    """``Runner`` sobre un subproceso asyncio: stdout y stderr juntos."""

    def _isolation(self) -> dict[str, Any]:
        """Popen options that put the child in its own session/group."""
        return {"start_new_session": True}

    def _kill_owned(self, proc: asyncio.subprocess.Process) -> None:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    async def run(
        self, cmd: Sequence[str], *, cwd: Path | None = None, env: Mapping[str, str] | None = None
    ) -> RunResult:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(cwd) if cwd else None,
                env={**os.environ, **env} if env else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                **self._isolation(),
            )
        except OSError as exc:
            return RunResult(rc=127, output=f"{cmd[0]}: {exc.strerror or exc}")
        try:
            out, _ = await proc.communicate()
        except asyncio.CancelledError:
            # pip and conversion may have children. Stop the entire owned
            # process group before the phase removes its staging directory.
            self._kill_owned(proc)
            await proc.communicate()
            raise
        return RunResult(rc=proc.returncode, output=out.decode(errors="replace").rstrip())
