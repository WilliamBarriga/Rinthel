"""Tail en vivo de un archivo de log, como widget reutilizable.

Antes LogsScreen tenía su propia corutina de tailing inline; ahora ese
widget lo comparten LogsScreen (panel completo) y MonitorScreen (panel
mini, opción [6] del menú) — sin duplicar el manejo del subproceso `tail -f`.
"""

import asyncio
from pathlib import Path

from textual.widgets import RichLog


class LogTail(RichLog):
    def __init__(self, path: Path, *, lines: int = 200, **kwargs) -> None:
        kwargs.setdefault("markup", False)
        kwargs.setdefault("auto_scroll", True)
        super().__init__(**kwargs)
        self._path = path
        self._lines = lines

    def on_mount(self) -> None:
        self.run_worker(self._tail(), exclusive=True)

    async def _tail(self) -> None:
        if not self._path.exists():
            self.write(f"Log no encontrado: {self._path}")
            return

        proc = await asyncio.create_subprocess_exec(
            "tail", "-n", str(self._lines), "-f", str(self._path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            assert proc.stdout is not None
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                self.write(line.decode(errors="replace").rstrip())
        finally:
            if proc.returncode is None:
                proc.terminate()
