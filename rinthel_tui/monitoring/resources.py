"""GPU/VRAM (nvidia-smi) y CPU/RAM (psutil) para MonitorScreen.

Reemplaza el comentario hardcodeado "confirmar con nvidia-smi bajo carga
real" de nc_llama_status_info por una métrica en vivo. Todo degrada a
"no disponible" en vez de romper si no hay GPU NVIDIA / nvidia-smi.
"""

import asyncio
from dataclasses import dataclass

import psutil


@dataclass(frozen=True)
class GpuSample:
    available: bool
    utilization: float | None = None  # %
    memory_used: float | None = None  # MiB
    memory_total: float | None = None  # MiB
    temperature: float | None = None  # °C
    power_draw: float | None = None  # W


def _num(raw: str) -> float | None:
    try:
        return float(raw)
    except ValueError:
        return None  # tolera campos "[N/A]" de nvidia-smi


async def read_gpu() -> GpuSample:
    try:
        proc = await asyncio.create_subprocess_exec(
            "nvidia-smi",
            "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw",
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


@dataclass(frozen=True)
class CpuRamSample:
    cpu_percent: float
    ram_used_gb: float
    ram_total_gb: float
    ram_percent: float


def _read_cpu_ram() -> CpuRamSample:
    cpu = psutil.cpu_percent(interval=None)
    vm = psutil.virtual_memory()
    gib = 1024**3
    return CpuRamSample(cpu, vm.used / gib, vm.total / gib, vm.percent)


async def read_cpu_ram() -> CpuRamSample:
    return await asyncio.to_thread(_read_cpu_ram)
