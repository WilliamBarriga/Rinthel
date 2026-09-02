"""Menú principal — reemplaza _menu_run_tui/_menu_run_plain (rinthel-boot.sh).

Fase 5 agrega [6] MONITOR y renumera EXIT a [7].
"""

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import OptionList, Static

from rinthel_tui.config import CONFIG
from rinthel_tui.lifecycle import specs
from rinthel_tui.tui.effects.transitions import AfterimageEffect, ChromaticAberrationEffect, SignalNoiseEffect
from rinthel_tui.tui.screens.capture import CaptureScreen
from rinthel_tui.tui.screens.farewell import FarewellScreen
from rinthel_tui.tui.screens.logs import LogsScreen
from rinthel_tui.tui.screens.monitor import MonitorScreen
from rinthel_tui.tui.screens.phase_runner import ClosingSequence, PhaseRunnerScreen
from rinthel_tui.tui.screens.reload import ReloadScreen
from rinthel_tui.tui.widgets.service_badge import ServiceBadge

_OPTIONS = (
    "[1] BOOT        -- Levantar todo (up)",
    "[2] RELOAD      -- Apagar + reiniciar completo",
    "[3] TERMINATE   -- Shutdown total",
    "[4] LOGS        -- Ver llama-server en vivo",
    "[5] CAPTURE     -- Capturar perfil MoE (routing profile)",
    "[6] MONITOR     -- Estado de servicios/Docker/GPU/CPU",
    "[7] EXIT        -- Cerrar terminal",
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
    def compose(self) -> ComposeResult:
        yield Static("◈ RINTHEL.AI -- NIGHT CITY COMMAND TERMINAL", classes="nc-divider")
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
        self.run_worker(self._handle_selection(event.option_index), exclusive=True)

    async def _handle_selection(self, index: int) -> None:
        if index == 0:
            await self.app.push_screen_wait(SignalNoiseEffect(1, 3, 20))
            self.app.push_screen(PhaseRunnerScreen("EXECUTE — FAST BOOT", specs.BOOT_PHASES, closing=_BOOT_CLOSING))
        elif index == 1:
            await self.app.push_screen_wait(SignalNoiseEffect(1, 3, 20))
            self.app.push_screen(ReloadScreen())
        elif index == 2:
            await self.app.push_screen_wait(SignalNoiseEffect(1, 3, 20))
            self.app.push_screen(
                PhaseRunnerScreen("SHUTDOWN SEQUENCE", specs.DOWN_PHASES, closing=_TERMINATE_CLOSING)
            )
        elif index == 3:
            self.app.push_screen(LogsScreen())
        elif index == 4:
            await self.app.push_screen_wait(SignalNoiseEffect(1, 3, 20))
            self.app.push_screen(CaptureScreen())
        elif index == 5:
            self.app.push_screen(MonitorScreen())
        elif index == 6:
            await self.app.push_screen_wait(FarewellScreen())
            self.app.exit()
