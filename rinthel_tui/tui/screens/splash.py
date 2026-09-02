"""Pantalla de arranque: reproduce rinthel-intro.txt, muestra el banner
duotono y espera cualquier tecla — reemplaza el tramo de _menu_run_tui en
rinthel-boot.sh que corre play_frames + show-rinthel-banner.sh antes de
abrir el dashboard del menú.
"""

from pathlib import Path

from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Static

from rinthel_tui.branding.banner import render_banner
from rinthel_tui.tui.effects.intro import IntroAnimation
from rinthel_tui.tui.screens.menu import MenuScreen

_INTRO_PATH = Path(__file__).parent.parent.parent / "branding" / "rinthel-intro.txt"


class SplashScreen(Screen):
    def compose(self) -> ComposeResult:
        with Vertical(id="splash"):
            yield IntroAnimation(
                _INTRO_PATH, fps=15, loops=1, id="intro-animation", on_finish=self._show_banner
            )

    def _show_banner(self) -> None:
        container = self.query_one("#splash", Vertical)
        self.query_one("#intro-animation").remove()
        container.mount(Static(render_banner(), classes="splash-title"))
        container.mount(Static("Presiona cualquier tecla para continuar…", classes="splash-prompt"))

    def on_key(self, event: events.Key) -> None:
        # Sin stop(): el mismo evento sigue bubbling y, si MenuScreen queda
        # activa y su OptionList enfocada dentro del mismo dispatch, ese
        # "enter" residual selecciona la opción resaltada por default (BOOT)
        # — dispararía la secuencia real de arranque sin que el usuario la
        # haya elegido.
        event.stop()
        self.app.push_screen(MenuScreen())
