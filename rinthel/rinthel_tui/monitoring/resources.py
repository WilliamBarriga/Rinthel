"""GPU/VRAM (nvidia-smi) y CPU/RAM (psutil) para MonitorScreen.

Reemplaza el comentario hardcodeado "confirmar con nvidia-smi bajo carga
real" de nc_llama_status_info por una métrica en vivo. Todo degrada a
"no disponible" en vez de romper si no hay GPU NVIDIA / nvidia-smi.
"""

import asyncio
from dataclasses import dataclass

import psutil

# Ceba el baseline de cpu_percent(interval=None) al importar el módulo: sin
# esto, la primerísima llamada devuelve 0.0 sin importar la carga real
# (psutil mide contra la llamada anterior, y la primera no tiene una).
psutil.cpu_percent(interval=None)


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


async def read_cpu_ram() -> CpuRamSample:
    # Sin asyncio.to_thread a propósito: cpu_percent()/virtual_memory() son
    # lecturas rápidas de /proc, no bloquean el loop — y psutil cachea el
    # baseline de cpu_percent *por thread* (ver _last_cpu_times en su
    # fuente), así que despachar esto a un worker thread rotativo del pool
    # de to_thread rompe la comparación y siempre da 0.0%.
    cpu = psutil.cpu_percent(interval=None)
    vm = psutil.virtual_memory()
    gib = 1024**3
    return CpuRamSample(cpu, vm.used / gib, vm.total / gib, vm.percent)
