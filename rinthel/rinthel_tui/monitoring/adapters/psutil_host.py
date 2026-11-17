"""``HostSensor`` sobre psutil."""

from __future__ import annotations

import psutil

from rinthel_tui.monitoring.domain.types import CpuRamSample

# Ceba el baseline de cpu_percent(interval=None) al importar el módulo: sin
# esto, la primerísima llamada devuelve 0.0 sin importar la carga real
# (psutil mide contra la llamada anterior, y la primera no tiene una).
psutil.cpu_percent(interval=None)

GIB = 1024**3


class PsutilHost:
    async def read(self) -> CpuRamSample:
        # Sin asyncio.to_thread a propósito: cpu_percent()/virtual_memory()
        # son lecturas rápidas de /proc, no bloquean el loop — y psutil
        # cachea el baseline de cpu_percent *por thread* (ver
        # _last_cpu_times en su fuente), así que despachar esto a un worker
        # thread rotativo del pool de to_thread rompe la comparación y
        # siempre da 0.0%.
        cpu = psutil.cpu_percent(interval=None)
        vm = psutil.virtual_memory()
        return CpuRamSample(float(cpu), vm.used / GIB, vm.total / GIB, float(vm.percent))
