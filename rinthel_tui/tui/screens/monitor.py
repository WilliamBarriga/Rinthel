"""[6] MONITOR — estado de servicios/Docker/GPU/CPU en vivo.

Capacidad nueva (no existía en el bash más allá de un curl throtled en el
footer del menú y un tail -f manual). Reemplaza el comentario hardcodeado
de nc_llama_status_info ("confirmar con nvidia-smi bajo carga real") por
métricas en vivo.
"""

import asyncio

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Static

from rinthel_tui.config import CONFIG, RinthelConfig
from rinthel_tui.lifecycle.services import LLAMA_SERVICE, PITHAGORAS_SERVICE, UNDERSTORY_SERVICE
from rinthel_tui.monitoring import resources, services
from rinthel_tui.tui.widgets.log_tail import LogTail
from rinthel_tui.tui.widgets.service_badge import ServiceBadge
from rinthel_tui.tui.widgets.sparkline import Sparkline

_POLL_DOCKER_S = 3.0
_POLL_GPU_S = 1.5
_POLL_CPU_S = 1.5


def _fmt(value: float | None, spec: str) -> str:
    """N/A en vez de "nan" para los campos "[N/A]" que nvidia-smi devuelve
    con la GPU idle (típicamente power.draw en GPUs de consumo)."""
    return spec.format(value) if value is not None else "N/A"


class MonitorScreen(Screen):
    BINDINGS = [("q", "close", "Volver"), ("escape", "close", "Volver")]

    def __init__(self, cfg: RinthelConfig | None = None) -> None:
        super().__init__()
        self.cfg = cfg or CONFIG
        self.docker_table: DataTable | None = None
        self.gpu_label: Static | None = None
        self.gpu_sparkline: Sparkline | None = None
        self.cpu_label: Static | None = None
        self.cpu_sparkline: Sparkline | None = None
        self.ram_sparkline: Sparkline | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="monitor-badges"):
            yield ServiceBadge.for_service(UNDERSTORY_SERVICE, self.cfg, id="mon-badge-understory")
            yield ServiceBadge.for_service(PITHAGORAS_SERVICE, self.cfg, id="mon-badge-pithagoras")
            yield ServiceBadge.for_service(LLAMA_SERVICE, self.cfg, id="mon-badge-llama")

        self.docker_table = DataTable(id="monitor-docker", classes="panel")
        self.docker_table.border_title = "◈ DOCKER STATUS"
        self.docker_table.add_columns("Contenedor", "Estado", "Puertos", "Uptime")
        yield self.docker_table

        with Horizontal(id="monitor-resources"):
            with Vertical(classes="monitor-panel panel"):
                self.gpu_label = Static("GPU: —", classes="nc-caution")
                yield self.gpu_label
                self.gpu_sparkline = Sparkline(id="gpu-sparkline")
                yield self.gpu_sparkline
            with Vertical(classes="monitor-panel panel"):
                self.cpu_label = Static("CPU/RAM: —", classes="nc-caution")
                yield self.cpu_label
                self.cpu_sparkline = Sparkline(id="cpu-sparkline")
                yield self.cpu_sparkline
                self.ram_sparkline = Sparkline(id="ram-sparkline")
                yield self.ram_sparkline

        log_tail = LogTail(self.cfg.llama.log, lines=50, id="monitor-log", classes="panel")
        log_tail.border_title = "◈ LLAMA-SERVER LOG"
        yield log_tail
        yield Static("q / Esc para volver", classes="nc-dim")

    def on_mount(self) -> None:
        self.run_worker(self._poll_docker(), exclusive=True, group="monitor-docker")
        self.run_worker(self._poll_gpu(), exclusive=True, group="monitor-gpu")
        self.run_worker(self._poll_cpu(), exclusive=True, group="monitor-cpu")

    async def _poll_docker(self) -> None:
        assert self.docker_table is not None
        while True:
            rows = []
            for directory in (self.cfg.understory.dir, self.cfg.pithagoras.dir):
                rows.extend(await services.docker_compose_ps(directory))
            self.docker_table.clear()
            if rows:
                for c in rows:
                    self.docker_table.add_row(c.name, c.state, c.ports, c.status)
            else:
                self.docker_table.add_row("—", "OFFLINE", "—", "—")
            await asyncio.sleep(_POLL_DOCKER_S)

    async def _poll_gpu(self) -> None:
        assert self.gpu_label is not None and self.gpu_sparkline is not None
        while True:
            sample = await resources.read_gpu()
            if sample.available and sample.utilization is not None:
                mem_used = _fmt(sample.memory_used, "{:.0f}")
                mem_total = _fmt(sample.memory_total, "{:.0f}")
                temp = _fmt(sample.temperature, "{:.0f}")
                power = _fmt(sample.power_draw, "{:.0f}")
                self.gpu_label.update(
                    f"GPU: {sample.utilization:.0f}%  VRAM {mem_used}/{mem_total} MiB"
                    f"  {temp}°C  {power}W"
                )
                self.gpu_sparkline.push(sample.utilization, max_value=100)
            else:
                self.gpu_label.update("GPU: N/A (sin nvidia-smi o sin GPU NVIDIA)")
                self.gpu_sparkline.push(None)
            await asyncio.sleep(_POLL_GPU_S)

    async def _poll_cpu(self) -> None:
        assert (
            self.cpu_label is not None and self.cpu_sparkline is not None and self.ram_sparkline is not None
        )
        while True:
            sample = await resources.read_cpu_ram()
            self.cpu_label.update(
                f"CPU {sample.cpu_percent:.0f}%   "
                f"RAM {sample.ram_used_gb:.1f}/{sample.ram_total_gb:.1f} GiB ({sample.ram_percent:.0f}%)"
            )
            self.cpu_sparkline.push(sample.cpu_percent, max_value=100)
            self.ram_sparkline.push(sample.ram_percent, max_value=100)
            await asyncio.sleep(_POLL_CPU_S)

    def action_close(self) -> None:
        self.app.pop_screen()
