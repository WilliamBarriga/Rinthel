"""Base para los efectos de transición.

Reemplaza el patrón hide_cursor + move_cursor absoluto + sleep_ms de
clifx/scripts/manifest_*.sh: cada TransitionEffect es un ModalScreen
efímero que se apila sobre lo que esté activo (mismo efecto visual que el
alt-screen del bash), corre su propia corutina ``run()`` — el mismo shape
imperativo del bash original, sin manejo manual de cursor — y se cierra
sola al terminar. Quien la dispara hace ``await
self.app.push_screen_wait(MiEfecto())`` y sigue cuando el efecto termina.
"""

from rich.segment import Segment
from rich.style import Style
from textual.screen import ModalScreen
from textual.strip import Strip

Cell = tuple[str, Style | None]
Grid = list[list[Cell]]


class TransitionEffect(ModalScreen[None]):
    """Subclases implementan ``async def run(self, width, height)``, que
    arma frames con ``self.set_frame(grid_to_strips(grid))`` espaciados por
    ``asyncio.sleep`` — igual que el while/sleep_ms del bash original."""

    DEFAULT_CSS = """
    TransitionEffect {
        background: $background 0%;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._rows: list[Strip] = []

    def on_mount(self) -> None:
        self.run_worker(self._run_and_dismiss(), exclusive=True)

    async def _run_and_dismiss(self) -> None:
        try:
            await self.run(self.size.width, self.size.height)
        finally:
            self.dismiss()

    async def run(self, width: int, height: int) -> None:
        raise NotImplementedError

    def set_frame(self, rows: list[Strip]) -> None:
        self._rows = rows
        self.refresh()

    def clear(self) -> None:
        self.set_frame([])

    def render_line(self, y: int) -> Strip:
        if 0 <= y < len(self._rows):
            return self._rows[y]
        return Strip.blank(self.size.width)


def blank_grid(width: int, height: int) -> Grid:
    """Grilla mutable de (char, style) — subclases la rellenan por frame."""
    return [[(" ", None) for _ in range(width)] for _ in range(height)]


def grid_to_strips(grid: Grid) -> list[Strip]:
    return [Strip([Segment(ch, style) for ch, style in row]) for row in grid]
