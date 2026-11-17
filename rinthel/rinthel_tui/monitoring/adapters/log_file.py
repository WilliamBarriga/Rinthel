"""``ServiceLog`` sobre el filesystem: ``tail -f`` del log de llama-server."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import BinaryIO

from rinthel_tui.clock import Clock, SystemClock
from rinthel_tui.config import RinthelConfig


def _last_lines(f: BinaryIO, end: int, n: int) -> tuple[list[str], bytes]:
    """Las últimas ``n`` líneas completas de ``f`` antes del offset ``end``,
    y lo que queda después del último salto de línea (una línea a medio
    escribir)."""
    block = min(end, 1 << 16)
    while True:
        f.seek(end - block)
        complete, _, partial = f.read(block).rpartition(b"\n")
        lines = complete.decode(errors="replace").splitlines()
        if len(lines) > n or block == end:
            return (lines[-n:] if n else []), partial
        block = min(block * 2, end)


async def tail(
    path: Path, *, backlog: int = 50, poll: float = 0.5, clock: Clock | None = None
) -> AsyncIterator[str]:
    """``tail -f`` de ``path``: las últimas ``backlog`` líneas y después lo
    que se agrega. Sin archivo, una sola línea de espera y polling hasta que
    aparezca; todo lo que tenga entonces es nuevo. Un archivo que desaparece
    vuelve a esa espera, sin reenviar el backlog. Un archivo rotado (otro
    inode) o truncado se relee desde el principio. Solo salen líneas
    completas: lo que sigue al último salto de línea espera a la próxima
    lectura. Lectura pura, nunca escribe. Cada ``poll`` segundos son del
    ``clock``."""
    clock = clock or SystemClock()
    ino, pos, pending = None, 0, b""
    try:
        with path.open("rb") as f:
            ino = os.fstat(f.fileno()).st_ino
            pos = f.seek(0, 2)
            lines, pending = _last_lines(f, pos, backlog)
    except FileNotFoundError:
        lines = []
    for line in lines:
        yield line
    while True:
        try:
            f = path.open("rb")
        except FileNotFoundError:
            yield f"[daemon] esperando {path}"
            while not path.exists():
                await clock.sleep(poll)
            ino, pos, pending = None, 0, b""
            continue
        with f:
            st = os.fstat(f.fileno())
            if st.st_ino != ino or st.st_size < pos:  # rotado o truncado
                ino, pos, pending = st.st_ino, 0, b""
            f.seek(pos)
            complete, _, pending = (pending + f.read()).rpartition(b"\n")
            pos = f.tell()
        for line in complete.decode(errors="replace").splitlines():
            if line:
                yield line
        await clock.sleep(poll)


class FileLog:
    """``cfg_of`` es el ``cfg`` vivo; ``poll`` cada cuánto, en segundos del
    ``clock``, se mira el archivo."""

    def __init__(self, cfg_of: Callable[[], RinthelConfig], *, poll: float = 0.5, clock: Clock | None = None) -> None:
        self._cfg_of = cfg_of
        self._poll = poll
        self._clock = clock

    def follow(self) -> AsyncIterator[str]:
        # El path se lee una vez por ``follow`` (una por conexión): un
        # cambio de ``llama.log`` se aplica al reconectar.
        return tail(self._cfg_of().llama.log, poll=self._poll, clock=self._clock)
