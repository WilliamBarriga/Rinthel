"""Reproductor de animaciones cuadro-a-cuadro en formato "--- Frame N ---".

Reemplaza play_frames (clifx/lib/ascii.sh). Sin _crop_frame: Textual ya
recorta/centra el contenido del widget según su tamaño, no hace falta
recortar el texto a mano por viewport.
"""

from pathlib import Path
from typing import Callable

from textual.timer import Timer
from textual.widgets import Static


def parse_frames(path: Path) -> list[str]:
    frames: list[str] = []
    current: list[str] = []
    for line in path.read_text().splitlines():
        if line.startswith("--- Frame"):
            if current:
                frames.append("\n".join(current))
            current = []
            continue
        current.append(line)
    if current:
        frames.append("\n".join(current))
    return frames


class IntroAnimation(Static):
    """Usage: IntroAnimation(path, fps=15, loops=1, on_finish=callback)."""

    def __init__(
        self,
        path: Path,
        *,
        fps: float = 15.0,
        loops: int = 1,
        on_finish: Callable[[], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._frames = parse_frames(path)
        self._fps = fps
        self._loops = loops
        self._on_finish = on_finish
        self._frame_index = 0
        self._loop_count = 0
        self._timer: Timer | None = None

    def on_mount(self) -> None:
        if not self._frames:
            if self._on_finish is not None:
                self._on_finish()
            return
        self.update(self._frames[0])
        self._timer = self.set_interval(1 / self._fps, self._advance)

    def _advance(self) -> None:
        self._frame_index += 1
        if self._frame_index >= len(self._frames):
            self._frame_index = 0
            self._loop_count += 1
            if self._loops and self._loop_count >= self._loops:
                if self._timer is not None:
                    self._timer.stop()
                if self._on_finish is not None:
                    self._on_finish()
                return
        self.update(self._frames[self._frame_index])
