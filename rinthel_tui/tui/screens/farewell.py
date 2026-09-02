"""Pantalla de cierre — reemplaza rinthel-outro.sh (nc_play_outro /
nc_show_farewell). El propio bash documentaba nc_farewell_content como
placeholder ("pensado para reemplazarse más adelante"); acá se omite el
effect_breathe previo — no está en el inventario de 8 efectos portados — y
se deja directo el glitch reveal del mensaje de cierre + una pausa.
"""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen

from rinthel_tui.tui.effects.flicker import GlitchLabel

FAREWELL_SECONDS = 5
MESSAGE = "RINTHEL.AI — SESSION CLOSED"


class FarewellScreen(Screen):
    def compose(self) -> ComposeResult:
        with Vertical(id="farewell"):
            yield GlitchLabel(MESSAGE, frames=14, id="farewell-message", classes="splash-title")

    def on_mount(self) -> None:
        self.set_timer(FAREWELL_SECONDS, self._finish)

    def _finish(self) -> None:
        # set_timer no debe recibir self.dismiss directo: dismiss() devuelve
        # un awaitable y Textual intenta esperarlo dentro del propio handler
        # de esta screen, lo cual está prohibido ("Can't await screen.dismiss()
        # from the screen's message handler"). Este wrapper sync lo descarta.
        self.dismiss()
