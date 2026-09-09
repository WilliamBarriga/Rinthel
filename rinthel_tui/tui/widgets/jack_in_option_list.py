"""OptionList con numeración "jack-in".

El espacio tras el `[N]` de la opción resaltada se reemplaza por un glifo
cíclico de ``palette.FRAME_CHARS``, mutando solo esa fila vía
``replace_option_prompt_at_index`` (O(1), sin reconstruir la lista) en vez
de reconstruir todo el ``OptionList`` en cada tick.
"""

import re

from textual.timer import Timer
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from rinthel_tui.theme import palette

_PROMPT_RE = re.compile(r"^(\[[^\]]+\])\s")


class JackInOptionList(OptionList):
    """Anima el prompt de la fila resaltada con un glifo tras su `[N]`."""

    def __init__(self, *options: Option, glyph_ms: int = 120, **kwargs) -> None:
        # OptionList.__init__ dispara action_first() -> self.highlighted = 0,
        # que invoca watch_highlighted() de forma síncrona ANTES de que este
        # __init__ termine -- estos atributos deben existir antes del
        # super().__init__() para que ese primer disparo no reviente.
        self._clean_prompts = {i: str(opt.prompt) for i, opt in enumerate(options)}
        self._glyph_ms = glyph_ms
        self._glyph_index = 0
        self._glyph_timer: Timer | None = None
        self._active_row: int | None = None
        super().__init__(*options, **kwargs)

    def watch_highlighted(self, highlighted: int | None) -> None:
        # Restaura la fila que pierde el foco ANTES de que super() procese
        # el nuevo highlighted, para no dejar un glifo "congelado" en ella.
        if self._active_row is not None:
            self._restore_row(self._active_row)
        self._active_row = None
        if self._glyph_timer is not None:
            self._glyph_timer.stop()
            self._glyph_timer = None

        super().watch_highlighted(highlighted)

        if highlighted is not None and not self._options[highlighted].disabled:
            self._active_row = highlighted
            self._advance_glyph()
            self._glyph_timer = self.set_interval(self._glyph_ms / 1000, self._advance_glyph)

    def _restore_row(self, index: int) -> None:
        clean = self._clean_prompts.get(index)
        if clean is None:
            return
        self.replace_option_prompt_at_index(index, _PROMPT_RE.sub(r"\1 ", clean, count=1))

    def _advance_glyph(self) -> None:
        if self._active_row is None:
            return
        clean = self._clean_prompts.get(self._active_row)
        if clean is None:
            return
        glyph = palette.FRAME_CHARS[self._glyph_index % len(palette.FRAME_CHARS)]
        self._glyph_index += 1
        self.replace_option_prompt_at_index(
            self._active_row, _PROMPT_RE.sub(rf"\1{glyph}", clean, count=1)
        )
