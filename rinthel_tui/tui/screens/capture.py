"""Screen de la opción [5] CAPTURE — corre capture_profile en foreground.

Reemplaza nightcity/tools/rinthel-capture-profile.sh. A diferencia de
PhaseRunnerScreen/ReloadScreen, capture_profile es una única función (no
una lista de PhaseSpec) con dos sub-pasos internos ('código' y 'chat') que
reporta como líneas de log — no necesita un checklist multi-fila.
"""

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import RichLog, Static

from rinthel_tui.config import CONFIG, RinthelConfig
from rinthel_tui.lifecycle.capture_profile import capture_profile
from rinthel_tui.lifecycle.phases import PhaseError
from rinthel_tui.tui.screens.phase_runner import ScreenPhaseReport


class CaptureScreen(Screen):
    BINDINGS = [("escape", "dismiss_if_done", "Volver")]

    def __init__(self, cfg: RinthelConfig | None = None) -> None:
        super().__init__()
        self.cfg = cfg or CONFIG
        self.status_widget: Static | None = None
        self.log_widget: RichLog | None = None
        self._done = False

    def compose(self) -> ComposeResult:
        yield Static("◈ MOE PROFILE CAPTURE — Qwen3.6-35B-A3B", classes="nc-divider")
        self.status_widget = Static("○ capturando perfil de expertos…", classes="phase-row phase-running")
        yield self.status_widget
        self.log_widget = RichLog(markup=True, id="capture-log")
        yield self.log_widget

    def on_mount(self) -> None:
        self.run_worker(self._run(), exclusive=True)

    async def _run(self) -> None:
        assert self.status_widget is not None and self.log_widget is not None
        report = ScreenPhaseReport(self.log_widget)
        try:
            await capture_profile(self.cfg, report)
        except PhaseError as exc:
            self.status_widget.update(f"✖ falló: {exc}")
            self.status_widget.set_classes("phase-row phase-error")
        else:
            self.status_widget.update(f"● perfil capturado — {self.cfg.moe_cache_profile}")
            self.status_widget.set_classes("phase-row phase-done")
        self._done = True

    def action_dismiss_if_done(self) -> None:
        if self._done:
            self.app.pop_screen()
