"""Orquesta las 3 tandas de rinthel-reload.sh (shutdown → boot → rebuild+up)
como una única sesión de checklist — igual que nc_tui_session_start
recibiendo el array plano de labels en el bash original. El total de fases
lo calcula specs.py solo, a partir de cuántos servicios haya registrados en
lifecycle/services.py.
"""

from rinthel_tui.config import RinthelConfig
from rinthel_tui.lifecycle import specs
from rinthel_tui.theme import palette
from rinthel_tui.tui.effects.transitions import DatamoshEffect, RippleEffect, VignetteEffect
from rinthel_tui.tui.screens.phase_runner import PhaseSequenceScreen, ScreenPhaseReport

_GROUPS = (specs.RELOAD_SHUTDOWN_PHASES, specs.RELOAD_BOOT_PHASES, specs.RELOAD_REBUILD_PHASES)


class ReloadScreen(PhaseSequenceScreen):
    def __init__(self, cfg: RinthelConfig | None = None) -> None:
        all_labels = [spec.label for group in _GROUPS for spec in group]
        super().__init__("SYSTEM REBOOT", all_labels, cfg)

    async def _on_shutdown_to_boot(self) -> None:
        # Corte de señal entre apagado y arranque — effect_datamosh en el bash.
        await self.app.push_screen_wait(DatamoshEffect(2, 2))

    async def _on_boot_to_rebuild(self) -> None:
        # Transición antes del rebuild — effect_vignette en el bash.
        await self.app.push_screen_wait(VignetteEffect(2, 2))

    async def _run_all(self) -> None:
        assert self.log_widget is not None
        report = ScreenPhaseReport(self.log_widget)
        transitions = (None, self._on_shutdown_to_boot, self._on_boot_to_rebuild)
        for group, transition in zip(_GROUPS, transitions):
            if transition is not None:
                await transition()
            for spec in group:
                if not await self._run_spec(spec, report):
                    self._done = True
                    return
        self.log_widget.write(f"[{palette.SUCCESS}]Reboot completo.[/]")
        # Remate "sincronización restaurada" — effect_ripple en el bash.
        await self.app.push_screen_wait(RippleEffect())
        self.log_widget.write(f"[{palette.SUCCESS}]◈ SYSTEM REBOOTED — TODOS LOS SERVICIOS ACTIVOS[/]")
        self._done = True
