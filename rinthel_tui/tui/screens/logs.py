"""Tail en vivo de $LOG (llama-server). Reemplaza _menu_view_log
(rinthel-boot.sh: tail -f + poll de teclas 'q'/ESC en el mismo alt-screen)."""

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static

from rinthel_tui.config import CONFIG, RinthelConfig
from rinthel_tui.tui.widgets.log_tail import LogTail


class LogsScreen(Screen):
    BINDINGS = [("q", "close", "Volver"), ("escape", "close", "Volver")]

    def __init__(self, cfg: RinthelConfig | None = None) -> None:
        super().__init__()
        self.cfg = cfg or CONFIG

    def compose(self) -> ComposeResult:
        yield Static("◈ LLAMA-SERVER LOG — q para volver", classes="nc-divider")
        yield LogTail(self.cfg.log, id="tail-log")

    def action_close(self) -> None:
        self.app.pop_screen()
