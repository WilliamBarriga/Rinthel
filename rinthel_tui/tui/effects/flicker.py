"""Efectos de texto inline — glitch reveal / flicker / typewriter / pulse.

Reemplaza clifx/lib/flicker.sh. ``glitch_frames`` es la ÚNICA implementación
de reveal-por-corrupción, reusada por banner/menú/farewell — el bash tenía
tres copias casi idénticas (nc_banner_glitch en night-city.sh,
_menu_glitch_options en rinthel-boot.sh, glitch_reveal en clifx/lib/flicker.sh)
que esta consolidación elimina de verdad.
"""

import asyncio
import random
from typing import Iterator

from textual.timer import Timer
from textual.widgets import Static

_CORRUPT_CHARS = "░▒▓█╳"


def glitch_frames(text: str, frames: int = 8) -> Iterator[str]:
    """`frames` strings que revelan `text` de izquierda a derecha a través
    de caracteres de corrupción; el último yield es siempre el texto limpio."""
    length = len(text)
    for f in range(frames):
        reveal = length * (f + 1) // frames
        out = []
        for i, ch in enumerate(text):
            if i < reveal or ch == " ":
                out.append(ch)
            else:
                out.append(random.choice(_CORRUPT_CHARS))
        yield "".join(out)
    yield text


class GlitchLabel(Static):
    """Widget que anima glitch_frames() sobre su propio texto al montar.
    Reemplaza nc_banner_glitch / _menu_glitch_options / glitch_reveal."""

    def __init__(self, text: str, *, frames: int = 8, frame_ms: int = 60, **kwargs) -> None:
        super().__init__(text, **kwargs)
        self._final_text = text
        self._frames = list(glitch_frames(text, frames))
        self._frame_ms = frame_ms
        self._index = 0
        self._timer: Timer | None = None

    def on_mount(self) -> None:
        self.update(self._frames[0])
        self._timer = self.set_interval(self._frame_ms / 1000, self._advance)

    def _advance(self) -> None:
        self._index += 1
        if self._index >= len(self._frames):
            self.update(self._final_text)
            if self._timer is not None:
                self._timer.stop()
            return
        self.update(self._frames[self._index])


class FlickerLabel(Static):
    """Reemplaza text_flicker: alterna reverse-video ON/OFF `times` veces."""

    def __init__(self, text: str, *, times: int = 3, frame_ms: int = 60, **kwargs) -> None:
        super().__init__(text, **kwargs)
        self._times = times
        self._frame_ms = frame_ms
        self._tick = 0
        self._timer: Timer | None = None

    def on_mount(self) -> None:
        self._timer = self.set_interval(self._frame_ms / 1000, self._advance)

    def _advance(self) -> None:
        self._tick += 1
        if self._tick >= self._times * 2:
            self.remove_class("-reverse")
            if self._timer is not None:
                self._timer.stop()
            return
        self.set_class(self._tick % 2 == 0, "-reverse")


class TypewriterLabel(Static):
    """Reemplaza text_wipe: revela un caracter por tick."""

    def __init__(self, text: str, *, char_ms: int = 30, **kwargs) -> None:
        super().__init__("", **kwargs)
        self._text = text
        self._char_ms = char_ms
        self._index = 0
        self._timer: Timer | None = None

    def on_mount(self) -> None:
        self._timer = self.set_interval(self._char_ms / 1000, self._advance)

    def _advance(self) -> None:
        self._index += 1
        self.update(self._text[: self._index])
        if self._index >= len(self._text):
            if self._timer is not None:
                self._timer.stop()


async def pulse(widget: Static, *, times: int = 5, duration: float = 0.15) -> None:
    """Reemplaza text_pulse: parpadeo de brillo vía widget.styles.animate()
    nativo de Textual, en vez de un loop manual de printf + sleep_ms."""
    for _ in range(times):
        widget.styles.animate("opacity", value=0.4, duration=duration)
        await asyncio.sleep(duration)
        widget.styles.animate("opacity", value=1.0, duration=duration)
        await asyncio.sleep(duration)
