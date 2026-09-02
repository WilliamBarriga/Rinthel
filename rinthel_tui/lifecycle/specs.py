"""Listas declarativas de fases — reemplaza los arrays RINTHEL_*_PHASES
de rinthel-up.sh/rinthel-down.sh/rinthel-reload.sh.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from rinthel_tui.config import RinthelConfig
from rinthel_tui.lifecycle import phases
from rinthel_tui.lifecycle.phases import PhaseReport

PhaseFn = Callable[..., Coroutine[Any, Any, None]]


@dataclass(frozen=True)
class PhaseSpec:
    label: str
    fn: PhaseFn
    kwargs: dict[str, Any] = field(default_factory=dict)

    async def run(self, cfg: RinthelConfig, report: PhaseReport) -> None:
        await self.fn(cfg, report, **self.kwargs)


# ── BOOT (rinthel-up.sh) ──────────────────────────────────────
BOOT_PHASES: list[PhaseSpec] = [
    PhaseSpec("◈ DOCKER", phases.phase_check_docker),
    PhaseSpec("◈ LLAMA-SERVER", phases.phase_spawn_llama_server),
    PhaseSpec("◈ ESPERANDO LLAMA-SERVER", phases.phase_wait_llama_ready),
    PhaseSpec("◈ UNDERSTORY  --  MCP MEMORY LAYER", phases.phase_up_understory),
    PhaseSpec("◈ PITHAGORAS  --  PI TASK PORTAL", phases.phase_build_up_pithagoras),
]

# ── DOWN (rinthel-down.sh) ────────────────────────────────────
DOWN_PHASES: list[PhaseSpec] = [
    PhaseSpec("◈ LLAMA-SERVER  --  Qwen3.6-35B-A3B-MTP", phases.phase_kill_llama_server),
    PhaseSpec("◈ UNDERSTORY  --  MCP MEMORY LAYER", phases.phase_stop_understory),
    PhaseSpec("◈ PITHAGORAS  --  PI TASK PORTAL", phases.phase_stop_pithagoras),
]

# ── RELOAD (rinthel-reload.sh) — 9 fases en 3 tandas ──────────
RELOAD_SHUTDOWN_PHASES: list[PhaseSpec] = [
    PhaseSpec("◈ [1/9] LLAMA-SERVER — parar", phases.phase_kill_llama_server),
    PhaseSpec("◈ [2/9] UNDERSTORY — parar", phases.phase_stop_understory),
    PhaseSpec("◈ [3/9] PITHAGORAS — parar", phases.phase_stop_pithagoras),
    PhaseSpec("◈ [4/9] PUERTO :8080 LIBRE", phases.phase_wait_port_free),
]

RELOAD_BOOT_PHASES: list[PhaseSpec] = [
    PhaseSpec("◈ [5/9] DOCKER", phases.phase_check_docker),
    PhaseSpec("◈ [6/9] LLAMA-SERVER — lanzar", phases.phase_spawn_llama_server),
    PhaseSpec("◈ [7/9] ESPERANDO LLAMA-SERVER", phases.phase_wait_llama_ready),
]

RELOAD_REBUILD_PHASES: list[PhaseSpec] = [
    PhaseSpec("◈ [8/9] UNDERSTORY — up", phases.phase_up_understory),
    PhaseSpec(
        "◈ [9/9] PITHAGORAS — rebuild + up",
        phases.phase_build_up_pithagoras,
        kwargs={"no_cache": True},
    ),
]
