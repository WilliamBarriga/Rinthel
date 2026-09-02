"""Pantalla de arranque: anima el banner duotono componiéndose desde ruido
y espera cualquier tecla — reemplaza el tramo de _menu_run_tui en
rinthel-boot.sh que corre play_frames + show-rinthel-banner.sh antes de
abrir el dashboard del menú. Una sola caja de principio a fin: la
animación arma el mismo banner que queda en pantalla, no una pieza
separada que luego es reemplazada por otra.
"""

from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Static

from rinthel_tui.branding.banner import compose_frames, render_banner
from rinthel_tui.tui.effects.intro import IntroAnimation
from rinthel_tui.tui.screens.menu import MenuScreen


class SplashScreen(Screen):
    def compose(self) -> ComposeResult:
        with Vertical(id="splash"):
            yield IntroAnimation(
                compose_frames(),
                fps=15,
                loops=1,
                id="intro-animation",
                classes="splash-title",
                on_finish=self._show_prompt,
            )

    def _show_prompt(self) -> None:
        intro = self.query_one("#intro-animation", Static)
        intro.update(render_banner())
        self.query_one("#splash", Vertical).mount(
            Static("Presiona cualquier tecla para continuar…", classes="splash-prompt")
        )

    def on_key(self, event: events.Key) -> None:
        # Sin stop(): el mismo evento sigue bubbling y, si MenuScreen queda
        # activa y su OptionList enfocada dentro del mismo dispatch, ese
        # "enter" residual selecciona la opción resaltada por default (BOOT)
        # — dispararía la secuencia real de arranque sin que el usuario la
        # haya elegido.
        event.stop()
        self.app.push_screen(MenuScreen())
