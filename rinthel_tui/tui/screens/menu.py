"""Menú principal — reemplaza _menu_run_tui/_menu_run_plain (rinthel-boot.sh).

Fase 5 agrega [6] MONITOR y renumera EXIT a [7]. [0] INSTALL agrega el setup
inicial de infra (CUDA/modelo/Pithagoras/Understory) para una máquina nueva.
"""

import random

from textual.app import ComposeResult
from textual.color import Color
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from rinthel_tui.branding.taglines import TAGLINES
from rinthel_tui.config import CONFIG, EFFECTS_ENABLED
from rinthel_tui.lifecycle import specs
from rinthel_tui.lifecycle.services import (
    PITHAGORAS_SERVICE,
    TTS_SERVICE,
    UNDERSTORY_SERVICE,
    WHISPER_SERVICE,
)
from rinthel_tui.theme import palette
from rinthel_tui.tui.effects.flicker import GlitchLabel
from rinthel_tui.tui.effects.tagline import RotatingTagline
from rinthel_tui.tui.effects.transitions import AfterimageEffect, ChromaticAberrationEffect, SignalNoiseEffect
from rinthel_tui.tui.screens.capture import CaptureScreen
from rinthel_tui.tui.screens.farewell import FarewellScreen
from rinthel_tui.tui.screens.logs import LogsScreen
from rinthel_tui.tui.screens.monitor import MonitorScreen
from rinthel_tui.tui.screens.phase_runner import ClosingSequence, PhaseRunnerScreen
from rinthel_tui.tui.screens.reload import ReloadScreen
from rinthel_tui.tui.widgets.jack_in_option_list import JackInOptionList
from rinthel_tui.tui.widgets.service_badge import ServiceBadge

# Ancho de arranque para los divisores — se usa en compose(), antes de que
# el widget esté montado (no hay size real todavía). on_mount() lo corrige
# al ancho medido real de #menu-options, que no coincide de forma fiable
# con el width nominal del CSS.
_DIVIDER_WIDTH_GUESS = 54

# Índices fijos de los 3 divisores dentro de #menu-options (la estructura
# del menú es estática — ver compose()). hot=True para los que anteceden
# una acción sin retorno ([3] TERMINATE, [7] EXIT); el de antes de
# [5] CAPTURE queda dim/informativo.
_DIVIDER_INDEX_1 = 3  # antes de [3] TERMINATE — hot
_DIVIDER_INDEX_2 = 6  # antes de [5] CAPTURE — dim
_DIVIDER_INDEX_3 = 9  # antes de [7] EXIT — hot


def _divider_markup(width: int, *, hot: bool = False) -> str:
    """3 glifos de palette.FRAME_CHARS sorteados al azar, en un patrón
    repetido hasta cubrir `width`. Color inline vía markup (pisa el $dim
    del component-class option-list--option-disabled)."""
    g1, g2, g3 = random.sample(palette.FRAME_CHARS, 3)
    unit = f"{g1}───{g2}───{g3}───"
    pattern = (unit * (width // len(unit) + 1))[:width]
    color = palette.HOT if hot else palette.DIM
    return f"[{color}]{pattern}[/]"


def _build_divider(width: int, *, hot: bool = False) -> Option:
    return Option(_divider_markup(width, hot=hot), disabled=True)


def _build_options(width: int) -> tuple[Option, ...]:
    """IDs explícitos en cada opción real: OptionList indexa TODAS las
    entradas (divisores incluidos), así que despachar por
    event.option_index es frágil ante cualquier reordenamiento.
    Despachamos por option_id en su lugar."""
    return (
        Option("[0] INSTALL     -- Setup inicial (CUDA/modelo/Pithagoras/Understory)", id="install"),
        Option("[1] BOOT        -- Levantar todo (up)", id="boot"),
        Option("[2] RELOAD      -- Apagar + reiniciar completo", id="reload"),
        _build_divider(width, hot=True),
        Option("[3] TERMINATE   -- Shutdown total", id="terminate"),
        Option("[4] LOGS        -- Ver llama-server en vivo", id="logs"),
        _build_divider(width, hot=False),
        Option("[5] CAPTURE     -- Capturar perfil MoE (routing profile)", id="capture"),
        Option("[6] MONITOR     -- Estado de servicios/Docker/GPU/CPU", id="monitor"),
        _build_divider(width, hot=True),
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

        # El width con el que se armaron los divisores en compose() era una
        # estimación (el widget no tiene size real antes de montarse); acá
        # ya se puede medir el ancho real de #menu-options y corregirlo.
        options = self.query_one("#menu-options", JackInOptionList)
        width = options.size.width
        if width:
            options.replace_option_prompt_at_index(_DIVIDER_INDEX_1, _divider_markup(width, hot=True))
            options.replace_option_prompt_at_index(_DIVIDER_INDEX_2, _divider_markup(width, hot=False))
            options.replace_option_prompt_at_index(_DIVIDER_INDEX_3, _divider_markup(width, hot=True))

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
            yield RotatingTagline(TAGLINES, id="menu-tagline", classes="tagline")
            yield JackInOptionList(*_build_options(_DIVIDER_WIDTH_GUESS), id="menu-options")
            with Horizontal(id="menu-footer"):
                yield ServiceBadge.for_service(UNDERSTORY_SERVICE, CONFIG, id="badge-understory")
                yield ServiceBadge.for_service(PITHAGORAS_SERVICE, CONFIG, id="badge-pithagoras")
                yield ServiceBadge.for_service(
                    WHISPER_SERVICE, CONFIG, label="Whisper STT", id="badge-whisper"
                )
                yield ServiceBadge.for_service(TTS_SERVICE, CONFIG, label="TTS", id="badge-tts")

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
