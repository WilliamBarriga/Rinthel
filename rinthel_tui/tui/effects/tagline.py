"""Tagline rotativo — reusa glitch_frames() de flicker.py para la transición
entre frases. Reusable por cualquier screen con título (no solo el menú)."""

import random
from typing import Sequence

from textual.timer import Timer
from textual.widgets import Static

from rinthel_tui.tui.effects.flicker import glitch_frames


class RotatingTagline(Static):
    """Cicla `lines` cada `interval_s`, revelando cada frase nueva con una
    transición glitch de `transition_frames` pasos — mismo algoritmo que
    GlitchLabel usa en su reveal inicial, aplicado en loop."""

    def __init__(
        self,
        lines: Sequence[str],
        *,
        interval_s: float = 6.0,
        shuffle: bool = True,
        transition_frames: int = 6,
        frame_ms: int = 40,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._lines = list(lines)
        if shuffle:
            random.shuffle(self._lines)
        self._interval_s = interval_s
        self._transition_frames = transition_frames
        self._frame_ms = frame_ms
        self._index = 0
        self._frames: list[str] = []
        self._frame_pos = 0
        self._frame_timer: Timer | None = None

    def on_mount(self) -> None:
        self.update(self._lines[0])
        self.set_interval(self._interval_s, self._start_transition)

    def _start_transition(self) -> None:
        self._index = (self._index + 1) % len(self._lines)
        self._frames = list(glitch_frames(self._lines[self._index], self._transition_frames))
        self._frame_pos = 0
        self.update(self._frames[0])
        self._frame_timer = self.set_interval(self._frame_ms / 1000, self._advance_frame)

    def _advance_frame(self) -> None:
        self._frame_pos += 1
        if self._frame_pos >= len(self._frames):
            if self._frame_timer is not None:
                self._frame_timer.stop()
            return
        self.update(self._frames[self._frame_pos])
