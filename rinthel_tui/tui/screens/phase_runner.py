"""Screen genérica para correr una lista de PhaseSpec con checklist + log.

Reemplaza el dashboard de nightcity-tui.sh (nc_tui_await/_nc_tui_draw) para
BOOT (rinthel-up.sh) y TERMINATE (rinthel-down.sh). ReloadScreen reusa la
base ``PhaseSequenceScreen`` para las 3 tandas de rinthel-reload.sh.
"""

from dataclasses import dataclass
from typing import Callable, Sequence

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import RichLog, Static

from rinthel_tui.config import CONFIG, RinthelConfig
from rinthel_tui.lifecycle.phases import PhaseReport
from rinthel_tui.lifecycle.runner import PhaseFailed, run_phase_list
from rinthel_tui.lifecycle.specs import PhaseSpec
from rinthel_tui.theme import palette
from rinthel_tui.tui.effects.base import TransitionEffect
from rinthel_tui.tui.screens.farewell import FarewellScreen
from rinthel_tui.tui.widgets.checklist import PhaseChecklist


class ScreenPhaseReport:
    """Adapta el protocolo PhaseReport a un RichLog con markup."""

    def __init__(self, log_widget: RichLog) -> None:
        self._log = log_widget

    def info(self, msg: str) -> None:
        self._log.write(f"  · {msg}")

    def success(self, msg: str) -> None:
        self._log.write(f"[{palette.SUCCESS}]  ● {msg}[/]")

    def warn(self, msg: str) -> None:
        self._log.write(f"[{palette.CAUTION}]  ▲ {msg}[/]")

    def error(self, msg: str) -> None:
        self._log.write(f"[{palette.HOT}]  ✖ {msg}[/]")


@dataclass(frozen=True)
class ClosingSequence:
    """Efecto + banner que cierra una secuencia exitosa — reemplaza el
    tramo final de rinthel-up.sh/rinthel-down.sh (effect_chromatic_aberration
    / effect_afterimage + nc_banner_glitch "SYSTEM ONLINE/OFFLINE")."""

    effect_factory: Callable[[], TransitionEffect]
    banner: str
    show_farewell: bool = False


class PhaseSequenceScreen(Screen):
    """Checklist + log de una secuencia de fases. Subclases implementan
    ``_run_all()``; usar ``_run_spec()`` por cada PhaseSpec que corran.

    Nota: el atributo se llama ``log_widget``, no ``log`` — ``log`` ya es
    una propiedad de Textual (Widget.log, su logger interno de depuración)
    y pisarla revienta con "property 'log' has no setter".
    """

    BINDINGS = [("escape", "dismiss_if_done", "Volver")]

    def __init__(self, title: str, labels: Sequence[str], cfg: RinthelConfig | None = None) -> None:
        super().__init__()
        self.session_title = title
        self.cfg = cfg or CONFIG
        self._labels = list(labels)
        self.checklist: PhaseChecklist | None = None
        self.log_widget: RichLog | None = None
        self._done = False

    def compose(self) -> ComposeResult:
        yield Static(self.session_title, classes="nc-divider")
        self.checklist = PhaseChecklist(self._labels, id="checklist")
        yield self.checklist
        self.log_widget = RichLog(markup=True, id="phase-log")
        yield self.log_widget
        yield Static("Ctrl+C para cancelar · Esc para volver al terminar", classes="nc-dim")

    def on_mount(self) -> None:
        self.run_worker(self._run_all(), exclusive=True)

    async def _run_spec(self, spec: PhaseSpec, report: PhaseReport) -> bool:
        """Corre una fase y refleja el resultado en el checklist. Devuelve
        False si la fase falló (la secuencia debe cortarse ahí). El corte
        en sí (catch de PhaseError, mensaje) vive en
        ``lifecycle.runner.run_phase_list`` — misma lógica que usa
        ``scripts/test_phases.py`` sin TUI, para no divergir entre los dos."""
        assert self.checklist is not None and self.log_widget is not None
        try:
            await run_phase_list(
                self.cfg, [spec], report,
                on_phase=lambda s, status: self.checklist.set_status(s.label, status),
            )
        except PhaseFailed as exc:
            self.log_widget.write(f"[{palette.HOT}]✖ secuencia cortada: {exc.cause}[/]")
            return False
        return True

    async def _run_closing(self, closing: ClosingSequence | None) -> None:
        assert self.log_widget is not None
        if closing is None:
            return
        await self.app.push_screen_wait(closing.effect_factory())
        self.log_widget.write(f"[{palette.SUCCESS}]◈ {closing.banner}[/]")
        if closing.show_farewell:
            await self.app.push_screen_wait(FarewellScreen())

    async def _run_all(self) -> None:
        raise NotImplementedError

    def action_dismiss_if_done(self) -> None:
        if self._done:
            self.app.pop_screen()


class PhaseRunnerScreen(PhaseSequenceScreen):
    """Usada por BOOT (specs.BOOT_PHASES) y TERMINATE (specs.DOWN_PHASES)."""

    def __init__(
        self,
        title: str,
        specs: Sequence[PhaseSpec],
        cfg: RinthelConfig | None = None,
        *,
        closing: ClosingSequence | None = None,
    ) -> None:
        super().__init__(title, [s.label for s in specs], cfg)
        self.specs = list(specs)
        self.closing = closing

    async def _run_all(self) -> None:
        assert self.log_widget is not None
        report = ScreenPhaseReport(self.log_widget)
        for spec in self.specs:
            if not await self._run_spec(spec, report):
                self._done = True
                return
        self.log_widget.write(f"[{palette.SUCCESS}]Secuencia completa.[/]")
        await self._run_closing(self.closing)
        self._done = True
