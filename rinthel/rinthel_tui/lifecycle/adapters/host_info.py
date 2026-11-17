import asyncio
import hashlib
import os
import shutil
from pathlib import Path

from rinthel_tui.lifecycle.domain.types import Platform


class SystemHostInfo:
    """``HostInfo`` de Linux sobre shutil, un glob del toolkit de CUDA, ``os``
    y hashlib. ``path`` y ``cuda_root`` son lo que varía: por defecto el
    ``PATH`` del entorno y ``/usr/local``. El de Windows es ``WindowsHostInfo``."""

    def __init__(self, *, path: str | None = None, cuda_root: Path = Path("/usr/local")) -> None:
        self._path = path
        self._cuda_root = cuda_root

    def platform(self) -> Platform:
        return "linux"

    def find_llama_server(self, build_dir: Path) -> Path | None:
        binary = build_dir / "bin" / "llama-server"
        return binary if binary.exists() else None

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
