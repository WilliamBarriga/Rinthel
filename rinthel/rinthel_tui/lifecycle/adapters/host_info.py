import asyncio
import hashlib
import os
import shutil
from pathlib import Path

from rinthel_tui.lifecycle.domain.types import Platform


class SystemHostInfo:
    """``HostInfo`` sobre shutil, un glob del toolkit de CUDA, ``os`` y hashlib.
    ``path``, ``cuda_root`` y ``os_name`` son lo que varía: por defecto el
    ``PATH`` del entorno, ``/usr/local`` y el ``os.name`` del proceso."""

    def __init__(
        self, *, path: str | None = None, cuda_root: Path = Path("/usr/local"), os_name: str = os.name
    ) -> None:
        self._path = path
        self._cuda_root = cuda_root
        self._os_name = os_name

    def platform(self) -> Platform:
        return "windows" if self._os_name == "nt" else "linux"

    def which(self, name: str) -> str | None:
        return shutil.which(name, path=self._path)

    def find_nvcc(self) -> str | None:
        if (on_path := self.which("nvcc")) is not None:
            return on_path
        found = sorted(self._cuda_root.glob("cuda*/bin/nvcc"))
        return str(found[0]) if found else None

    def cpu_count(self) -> int:
        return os.cpu_count() or 1

    async def sha256(self, path: Path) -> str:
        return await asyncio.to_thread(_sha256, path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()
