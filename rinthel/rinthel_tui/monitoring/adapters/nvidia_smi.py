"""``GpuSensor`` sobre ``nvidia-smi``. Degrada a ``available=False`` en vez de
romper si no hay GPU NVIDIA o ``nvidia-smi``."""

from __future__ import annotations

import asyncio

from rinthel_tui.monitoring.domain.types import GpuSample

QUERY = "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw"


def _num(raw: str) -> float | None:
    try:
        return float(raw)
    except ValueError:
        return None  # tolera campos "[N/A]" de nvidia-smi


class NvidiaSmiGpu:
    """``executable`` es el ``nvidia-smi`` a correr (el del ``PATH`` por
    defecto); los tests pasan uno falso."""

    def __init__(self, executable: str = "nvidia-smi") -> None:
        self._executable = executable

    async def read(self) -> GpuSample:
        try:
            proc = await asyncio.create_subprocess_exec(
                self._executable,
                QUERY,
                "--format=csv,noheader,nounits",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            out, _ = await proc.communicate()
        except OSError:
            return GpuSample(available=False)
        if proc.returncode != 0:
            return GpuSample(available=False)

        first_line = out.decode(errors="replace").strip().splitlines()
        if not first_line:
            return GpuSample(available=False)
        fields = [f.strip() for f in first_line[0].split(",")]
        if len(fields) < 5:
            return GpuSample(available=False)

        util, mem_used, mem_total, temp, power = (_num(f) for f in fields[:5])
        return GpuSample(True, util, mem_used, mem_total, temp, power)
