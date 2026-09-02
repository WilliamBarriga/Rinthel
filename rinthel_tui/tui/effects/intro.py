"""Reproductor de animaciones cuadro-a-cuadro sobre una lista de frames ya
renderizados (str o Rich renderable) — reemplaza play_frames (clifx/lib/
ascii.sh). Sin _crop_frame: Textual ya recorta/centra el contenido del
widget según su tamaño, no hace falta recortar el texto a mano por
viewport.
"""

from typing import Callable

from rich.console import RenderableType
from textual.timer import Timer
from textual.widgets import Static


class IntroAnimation(Static):
    """Usage: IntroAnimation(frames, fps=15, loops=1, on_finish=callback).

    `frames` es la secuencia ya construida (p.ej. banner.compose_frames()):
    este widget solo hace de reproductor, no sabe nada de banners.
    """

    def __init__(
        self,
        frames: list[RenderableType],
        *,
        fps: float = 15.0,
        loops: int = 1,
        on_finish: Callable[[], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._frames = frames
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
