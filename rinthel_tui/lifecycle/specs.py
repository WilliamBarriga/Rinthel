"""Listas declarativas de fases — reemplaza los arrays RINTHEL_*_PHASES
de rinthel-up.sh/rinthel-down.sh/rinthel-reload.sh.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from rinthel_tui.config import RinthelConfig
from rinthel_tui.lifecycle import install, phases
from rinthel_tui.lifecycle.phases import PhaseReport

PhaseFn = Callable[..., Coroutine[Any, Any, None]]


@dataclass(frozen=True)
class PhaseSpec:
    label: str
    fn: PhaseFn
    kwargs: dict[str, Any] = field(default_factory=dict)

    async def run(self, cfg: RinthelConfig, report: PhaseReport) -> None:
        await self.fn(cfg, report, **self.kwargs)


# ── INSTALL (bootstrap de infra en máquina nueva) ─────────────
# Configura, no bootea — termina indicando que uses [1] BOOT.
INSTALL_PHASES: list[PhaseSpec] = [
    PhaseSpec("◈ [1/6] PREFLIGHT — GPU/CUDA/cmake/docker", install.phase_install_preflight),
    PhaseSpec("◈ [2/6] LLAMA.CPP — clone", install.phase_install_clone_llamacpp),
    PhaseSpec("◈ [3/6] LLAMA.CPP — build CUDA (native)", install.phase_install_build_llamacpp),
    PhaseSpec("◈ [4/6] MODELO GGUF — descarga", install.phase_install_download_model),
    PhaseSpec("◈ [5/6] PITHAGORAS — clone + configurar", install.phase_install_setup_pithagoras),
    PhaseSpec("◈ [6/6] UNDERSTORY — scaffold + configurar", install.phase_install_setup_understory),
]

# ── BOOT (rinthel-up.sh) ──────────────────────────────────────
BOOT_PHASES: list[PhaseSpec] = [
    PhaseSpec("◈ DOCKER", phases.phase_check_docker),
    PhaseSpec("◈ LLAMA-SERVER", phases.phase_spawn_llama_server),
    PhaseSpec("◈ ESPERANDO LLAMA-SERVER", phases.phase_wait_llama_ready),
    PhaseSpec("◈ WHISPER — STT", phases.phase_spawn_whisper_server),
    PhaseSpec("◈ ESPERANDO WHISPER", phases.phase_wait_whisper_ready),
    PhaseSpec("◈ TTS — PIPER", phases.phase_spawn_tts_server),
    PhaseSpec("◈ ESPERANDO TTS", phases.phase_wait_tts_ready),
    PhaseSpec("◈ UNDERSTORY  --  MCP MEMORY LAYER", phases.phase_up_understory),
    PhaseSpec("◈ PITHAGORAS  --  PI TASK PORTAL", phases.phase_build_up_pithagoras),
]

# ── DOWN (rinthel-down.sh) ────────────────────────────────────
DOWN_PHASES: list[PhaseSpec] = [
    PhaseSpec("◈ LLAMA-SERVER  --  Qwen3.6-35B-A3B-MTP", phases.phase_kill_llama_server),
    PhaseSpec("◈ WHISPER — STT", phases.phase_kill_whisper_server),
    PhaseSpec("◈ TTS — PIPER", phases.phase_kill_tts_server),
    PhaseSpec("◈ UNDERSTORY  --  MCP MEMORY LAYER", phases.phase_stop_understory),
    PhaseSpec("◈ PITHAGORAS  --  PI TASK PORTAL", phases.phase_stop_pithagoras),
]

# ── RELOAD (rinthel-reload.sh) — 15 fases en 3 tandas ─────────
RELOAD_SHUTDOWN_PHASES: list[PhaseSpec] = [
    PhaseSpec("◈ [1/15] LLAMA-SERVER — parar", phases.phase_kill_llama_server),
    PhaseSpec("◈ [2/15] WHISPER — parar", phases.phase_kill_whisper_server),
    PhaseSpec("◈ [3/15] TTS — parar", phases.phase_kill_tts_server),
    PhaseSpec("◈ [4/15] UNDERSTORY — parar", phases.phase_stop_understory),
    PhaseSpec("◈ [5/15] PITHAGORAS — parar", phases.phase_stop_pithagoras),
    PhaseSpec("◈ [6/15] PUERTO :8080 LIBRE", phases.phase_wait_port_free),
]

RELOAD_BOOT_PHASES: list[PhaseSpec] = [
    PhaseSpec("◈ [7/15] DOCKER", phases.phase_check_docker),
    PhaseSpec("◈ [8/15] LLAMA-SERVER — lanzar", phases.phase_spawn_llama_server),
    PhaseSpec("◈ [9/15] ESPERANDO LLAMA-SERVER", phases.phase_wait_llama_ready),
    PhaseSpec("◈ [10/15] WHISPER — lanzar", phases.phase_spawn_whisper_server),
    PhaseSpec("◈ [11/15] ESPERANDO WHISPER", phases.phase_wait_whisper_ready),
    PhaseSpec("◈ [12/15] TTS — lanzar", phases.phase_spawn_tts_server),
    PhaseSpec("◈ [13/15] ESPERANDO TTS", phases.phase_wait_tts_ready),
]

RELOAD_REBUILD_PHASES: list[PhaseSpec] = [
    PhaseSpec("◈ [14/15] UNDERSTORY — up", phases.phase_up_understory),
    PhaseSpec(
        "◈ [15/15] PITHAGORAS — rebuild + up",
        phases.phase_build_up_pithagoras,
        kwargs={"no_cache": True},
    ),
]
