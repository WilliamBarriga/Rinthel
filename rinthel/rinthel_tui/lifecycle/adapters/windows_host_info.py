"""``HostInfo`` of Windows: the discovery validated on the reference machine
(``docs/05-windows-validation.md``). It reuses the Linux adapter for what is
the same and adds where Windows installs the build tools: the CMake bundled
with Visual Studio, ``CUDA_PATH`` and the standard CUDA toolkit directory, and
the multi-config ``Release`` directory of the llama.cpp build."""

import os
import re
from collections.abc import Mapping
from pathlib import Path

from rinthel_tui.lifecycle.adapters.host_info import SystemHostInfo
from rinthel_tui.lifecycle.domain.types import Platform

_VS_CMAKE = "*/*/Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe"


class WindowsHostInfo(SystemHostInfo):
    """``path`` and ``env`` are what varies: by default the process ``PATH`` and
    environment (``ProgramFiles``, ``CUDA_PATH``)."""

    def __init__(self, *, path: str | None = None, env: Mapping[str, str] | None = None) -> None:
        super().__init__(path=path)
        self._env = os.environ if env is None else env

    def platform(self) -> Platform:
        return "windows"

    def user_ids(self) -> tuple[int, int] | None:
        # Docker Desktop maps bind mounts itself: no host uid/gid to run as.
        return None

    def group_id(self, name: str) -> int | None:
        return None

    def _program_files(self) -> Path:
        return Path(self._env.get("ProgramFiles", r"C:\Program Files"))

    def which(self, name: str) -> str | None:
        found = super().which(name)
        if found is None and name == "cmake":
            return self._visual_studio_cmake()
        return found

    def _visual_studio_cmake(self) -> str | None:
        found = sorted((self._program_files() / "Microsoft Visual Studio").glob(_VS_CMAKE))
        return str(found[-1]) if found else None

    def find_nvcc(self) -> str | None:
        if (on_path := super().which("nvcc")) is not None:
            return on_path
        if cuda_path := self._env.get("CUDA_PATH"):
            candidate = Path(cuda_path) / "bin" / "nvcc.exe"
            if candidate.exists():
                return str(candidate)
        toolkits = (self._program_files() / "NVIDIA GPU Computing Toolkit" / "CUDA").glob("v*/bin/nvcc.exe")
        newest = sorted(toolkits, key=lambda nvcc: _version(nvcc.parents[1].name))
        return str(newest[-1]) if newest else None

    def find_llama_server(self, build_dir: Path) -> Path | None:
        # Visual Studio is multi-config: the binary lands in bin/Release.
        candidates = (build_dir / "bin" / "Release" / "llama-server.exe", build_dir / "bin" / "llama-server.exe")
        return next((candidate for candidate in candidates if candidate.exists()), None)


def _version(directory: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", directory))
