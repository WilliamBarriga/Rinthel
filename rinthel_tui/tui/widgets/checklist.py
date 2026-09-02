"""Widget reactivo de checklist de fases.

Reemplaza ``checklist_item`` (clifx/lib/progress.sh) + el redibujado manual
por coordenadas de cursor de ``_nc_tui_draw`` (nightcity-tui.sh): acá cada
fila es un ``Static`` que se actualiza sola vía ``set_status``, Textual se
encarga del repintado.
"""

from typing import Sequence

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from rinthel_tui.theme.palette import FRAME_CHARS

_ICONS = {
    "pending": "○",
    "done": "●",
    "warn": "▲",
    "error": "✖",
}


class PhaseChecklist(Vertical):
    """Una fila por label, con estado pending/running/done/warn/error."""

    def __init__(self, labels: Sequence[str], *, id: str | None = None) -> None:
        super().__init__(id=id)
        self._labels = list(labels)
        self._rows: dict[str, Static] = {}
        self._spin_index = 0

    def compose(self) -> ComposeResult:
        for label in self._labels:
            row = Static(f"○ {label}", classes="phase-row phase-pending")
            self._rows[label] = row
            yield row

    def set_status(self, label: str, status: str) -> None:
        row = self._rows.get(label)
        if row is None:
            return
        row.remove_class("phase-pending", "phase-running", "phase-done", "phase-warn", "phase-error")
        row.add_class(f"phase-{status}")
        icon = FRAME_CHARS[self._spin_index % len(FRAME_CHARS)] if status == "running" else _ICONS.get(status, "○")
        row.update(f"{icon} {label}")

    def tick_spinner(self) -> None:
        """Avanza el frame del spinner de las filas en estado running."""
        self._spin_index += 1
        icon = FRAME_CHARS[self._spin_index % len(FRAME_CHARS)]
        for label, row in self._rows.items():
            if row.has_class("phase-running"):
                row.update(f"{icon} {label}")
