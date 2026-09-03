"""Menú principal — reemplaza _menu_run_tui/_menu_run_plain (rinthel-boot.sh).

Fase 5 agrega [6] MONITOR y renumera EXIT a [7]. [0] INSTALL agrega el setup
inicial de infra (CUDA/modelo/Pithagoras/Understory) para una máquina nueva.
"""

from textual.app import ComposeResult
from textual.color import Color
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from rinthel_tui.config import CONFIG, EFFECTS_ENABLED
from rinthel_tui.lifecycle import specs
from rinthel_tui.theme import palette
from rinthel_tui.tui.effects.flicker import GlitchLabel
from rinthel_tui.tui.effects.transitions import AfterimageEffect, ChromaticAberrationEffect, SignalNoiseEffect
from rinthel_tui.tui.screens.capture import CaptureScreen
from rinthel_tui.tui.screens.farewell import FarewellScreen
from rinthel_tui.tui.screens.logs import LogsScreen
from rinthel_tui.tui.screens.monitor import MonitorScreen
from rinthel_tui.tui.screens.phase_runner import ClosingSequence, PhaseRunnerScreen
from rinthel_tui.tui.screens.reload import ReloadScreen
from rinthel_tui.tui.widgets.service_badge import ServiceBadge

# Separadores temáticos — opciones disabled (estilo via component-class
# nativo "option-list--option-disabled"; Option no admite kwarg `classes`)
_DIVIDER_1 = Option("⊹───◆───∴", disabled=True)
_DIVIDER_2 = Option("⊛───▓───⌇", disabled=True)
_DIVIDER_3 = Option("◈───▲───∷", disabled=True)

# IDs explícitos en cada opción real: OptionList indexa TODAS las entradas
# (divisores incluidos), así que despachar por event.option_index es frágil
# ante cualquier reordenamiento. Despachamos por option_id en su lugar.
_OPTIONS = (
    Option("[0] INSTALL     -- Setup inicial (CUDA/modelo/Pithagoras/Understory)", id="install"),
    Option("[1] BOOT        -- Levantar todo (up)", id="boot"),
    Option("[2] RELOAD      -- Apagar + reiniciar completo", id="reload"),
    _DIVIDER_1,
    Option("[3] TERMINATE   -- Shutdown total", id="terminate"),
    Option("[4] LOGS        -- Ver llama-server en vivo", id="logs"),
    _DIVIDER_2,
    Option("[5] CAPTURE     -- Capturar perfil MoE (routing profile)", id="capture"),
    Option("[6] MONITOR     -- Estado de servicios/Docker/GPU/CPU", id="monitor"),
    _DIVIDER_3,
    Option("[7] EXIT        -- Cerrar terminal", id="exit"),
)

_INSTALL_CLOSING = ClosingSequence(
    effect_factory=lambda: ChromaticAberrationEffect("SETUP LISTO", 1),
    banner="SETUP LISTO — elegí [1] BOOT para levantar todo",
)
_BOOT_CLOSING = ClosingSequence(
    effect_factory=lambda: ChromaticAberrationEffect("SYSTEM ONLINE", 1),
    banner="TODO EN LINEA — Understory + Pithagoras activos",
)
_TERMINATE_CLOSING = ClosingSequence(
    effect_factory=lambda: AfterimageEffect("SYSTEM OFFLINE"),
    banner="SYSTEM OFFLINE — TODOS LOS SERVICIOS DETENIDOS",
    show_farewell=True,
)


class MenuScreen(Screen):
    def on_mount(self) -> None:
        if EFFECTS_ENABLED:
            self._border_state = "magenta"
            self.set_interval(1.5, self._pulse_border)

    def _pulse_border(self) -> None:
        box = self.query_one("#menu-box")
        if self._border_state == "magenta":
            box.styles.border = ("double", Color.parse(palette.FG))       # cyan double
            self._border_state = "cyan"
        else:
            box.styles.border = ("solid", Color.parse(palette.ACCENT))    # magenta solid
            self._border_state = "magenta"

    def compose(self) -> ComposeResult:
        with Vertical(id="menu-box"):
            yield GlitchLabel(
                "◈ RINTHEL.AI -- NIGHT CITY COMMAND TERMINAL",
                frames=12, frame_ms=50,
                classes="menu-title", id="menu-title",
            )
            yield OptionList(*_OPTIONS, id="menu-options")
            with Horizontal(id="menu-footer"):
                yield ServiceBadge(
                    "Understory", f"http://localhost:{CONFIG.understory_port}", id="badge-understory"
                )
                yield ServiceBadge(
                    "Pithagoras", f"http://localhost:{CONFIG.pithagoras_port}", id="badge-pithagoras"
                )

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        # push_screen_wait exige correr dentro de un worker (get_current_worker()
        # falla si no) -- un handler `async def on_*` de Textual NO cuenta como
        # worker por sí solo, así que hace falta este run_worker explícito.
        self.run_worker(self._handle_selection(event.option_id), exclusive=True)

    async def _handle_selection(self, option_id: str | None) -> None:
        if option_id == "install":
            await self.app.push_screen_wait(SignalNoiseEffect(1, 3, 20))
            self.app.push_screen(
                PhaseRunnerScreen("INSTALL — SETUP INICIAL", specs.INSTALL_PHASES, closing=_INSTALL_CLOSING)
            )
        elif option_id == "boot":
            await self.app.push_screen_wait(SignalNoiseEffect(1, 3, 20))
            self.app.push_screen(PhaseRunnerScreen("EXECUTE — FAST BOOT", specs.BOOT_PHASES, closing=_BOOT_CLOSING))
        elif option_id == "reload":
            await self.app.push_screen_wait(SignalNoiseEffect(1, 3, 20))
            self.app.push_screen(ReloadScreen())
        elif option_id == "terminate":
            await self.app.push_screen_wait(SignalNoiseEffect(1, 3, 20))
            self.app.push_screen(
                PhaseRunnerScreen("SHUTDOWN SEQUENCE", specs.DOWN_PHASES, closing=_TERMINATE_CLOSING)
            )
        elif option_id == "logs":
            self.app.push_screen(LogsScreen())
        elif option_id == "capture":
            await self.app.push_screen_wait(SignalNoiseEffect(1, 3, 20))
            self.app.push_screen(CaptureScreen())
        elif option_id == "monitor":
            self.app.push_screen(MonitorScreen())
        elif option_id == "exit":
            await self.app.push_screen_wait(FarewellScreen())
            self.app.exit()
