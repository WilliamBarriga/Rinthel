"""Única fuente de verdad para paths/puertos de infra.

Reemplaza ``nightcity/config/rinthel-env.sh``. A diferencia del bash, no hace
falta un patrón de "exportar todo arriba": las fases reciben ``cfg``
explícito como argumento (no leen el entorno global), así que no importa en
qué orden ni en qué proceso/subshell corran.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path


def _p(path: str) -> Path:
    return Path(path).expanduser()


@dataclass(frozen=True)
class RinthelConfig:
    # ── LLAMA-SERVER ──────────────────────────────
    llama_env: dict[str, str]
    bin: Path
    model: Path
    port: int
    log: Path

    # Captura del perfil de ruteo de expertos — ver lifecycle/capture_profile.py
    moe_trace_build: Path
    moe_trace_out_dir: Path
    moe_cache_profile: Path

    # ── UNDERSTORY (MCP memory layer) ─────────────
    understory_dir: Path
    understory_port: int

    # ── PITHAGORAS (task portal) ──────────────────
    pithagoras_dir: Path
    pithagoras_port: int

    def apply_env(self) -> None:
        """Aplica llama_env al entorno del proceso (llamar una vez al arrancar)."""
        os.environ.update(self.llama_env)
        self.log.parent.mkdir(parents=True, exist_ok=True)


def default_config() -> RinthelConfig:
    moe_cache_profile = _p("~/codacus/profiles/qwen3.6-merged.csv")
    return RinthelConfig(
        llama_env={
            "GGML_CUDA_REGISTER_HOST": "1",
            "GGML_SCHED_PREFETCH_EXPERTS": "1",
            "GGML_MOE_CACHE_PROFILE": str(moe_cache_profile),
            "GGML_MOE_CACHE_SLOTS": "10",
        },
        bin=_p("~/codacus/llama.cpp/build-cuda/bin/llama-server"),
        model=_p("~/llama.cpp/models/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf"),
        port=8080,
        log=_p("~/CodeBase/.pi_profiles/logs/use-local-qwen3.6-tarkark-experimental.log"),
        moe_trace_build=_p("~/codacus/llama.cpp/build-cuda/bin/llama-moe-trace"),
        moe_trace_out_dir=_p("~/codacus/profiles"),
        moe_cache_profile=moe_cache_profile,
        understory_dir=_p("~/understory-poc"),
        understory_port=3800,
        pithagoras_dir=_p("~/pithagoras"),
        pithagoras_port=4100,
    )


CONFIG = default_config()
