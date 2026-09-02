"""Sparkline Unicode de las últimas N muestras.

Capacidad nueva de MonitorScreen (Fase 5) — clifx tiene cpu_sparkline/etc.
en scripts/manifest_data.sh, pero ese módulo nunca llegó a wirearse en
Rinthel (ver CLAUDE.md de clifx: "⚠ Unwired Effect Modules"), así que esto
no es un port sino una reimplementación directa contra psutil/nvidia-smi.
Tolera muestras ``None`` (campos "[N/A]" de nvidia-smi con la GPU inactiva).
"""

from collections import deque

from textual.widgets import Static

_BARS = " ▁▂▃▄▅▆▇█"


class Sparkline(Static):
    def __init__(self, *, maxlen: int = 60, **kwargs) -> None:
        super().__init__(**kwargs)
        self._samples: deque[float | None] = deque(maxlen=maxlen)

    def push(self, value: float | None, *, max_value: float = 100.0) -> None:
        self._samples.append(value)
        self._redraw(max_value)

    def _redraw(self, max_value: float) -> None:
        chars = []
        for v in self._samples:
            if v is None:
                chars.append("·")
                continue
            frac = 0.0 if max_value <= 0 else max(0.0, min(1.0, v / max_value))
            idx = round(frac * (len(_BARS) - 1))
            chars.append(_BARS[idx])
        self.update("".join(chars) if chars else "…")
