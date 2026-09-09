"""Única fuente de verdad para paths/puertos de infra.

Reemplaza ``nightcity/config/rinthel-env.sh``. A diferencia del bash, no hace
falta un patrón de "exportar todo arriba": las fases reciben ``cfg``
explícito como argumento (no leen el entorno global), así que no importa en
qué orden ni en qué proceso/subshell corran.

Todo campo de ``RinthelConfig`` puede overridearse con una var de entorno
``RINTHEL_*`` (ver ``.env.example``). Si existe un ``.env`` en la raíz de
este repo, se carga automáticamente vía ``python-dotenv`` antes de leer el
entorno — sin ``.env``, los defaults de ``default_config()`` quedan
idénticos al comportamiento anterior.
"""

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# find_dotenv()/load_dotenv() sin argumentos busca a partir del cwd del
# proceso, no de este archivo — si el TUI se lanza desde fuera del repo
# (p. ej. el menú principal, o cualquier launcher con otro cwd), el .env
# queda mudo y default_config() vuelve a sus defaults (context_window=112000
# en vez de lo que diga .env), sin ningún aviso. Anclamos la búsqueda a la
# raíz del repo (padre de este archivo) para que sea independiente del cwd.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _p(path: str) -> Path:
    return Path(path).expanduser()


def _str_env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _path_env(name: str, default: str) -> Path:
    return _p(os.environ.get(name, default))


def _int_env(name: str, default: int) -> int:
    val = os.environ.get(name, "").strip()
    return int(val) if val else default


def _float_env(name: str, default: float) -> float:
    val = os.environ.get(name, "").strip()
    return float(val) if val else default


def _bool_env(name: str, default: bool) -> bool:
    val = os.environ.get(name, "").strip().lower()
    if not val:
        return default
    return val in ("1", "on", "true", "yes")


@dataclass(frozen=True)
class RinthelConfig:
    # ── LLAMA-SERVER (binario y modelo) ───────────
    llama_env: dict[str, str]
    bin: Path
    model: Path
    port: int
    log: Path

    # ── MOE TRACE ───────────────────────────────
    moe_trace_build: Path
    moe_trace_out_dir: Path
    moe_cache_profile: Path

    # ── UNDERSTORY (MCP memory layer) ─────────────
    understory_dir: Path
    understory_port: int

    # ── PITHAGORAS (task portal) ──────────────────
    pithagoras_dir: Path
    pithagoras_port: int

    # ── INSTALL (bootstrap de infra en máquina nueva) ─────
    llamacpp_repo_dir: Path
    llamacpp_repo_url: str
    model_download_url: str
    pithagoras_repo_url: str
    workspaces_dir: Path
    pi_agent_dir: Path

    # ── LLAMA-SERVER (flags de inferencia) ────────
    # Valores por defecto idénticos a los hardcodeados originalmente en
    # phases.py. Dataclass exige que estos campos (con default) vayan
    # después de todos los que no tienen default.
    ngl: str = "all"                     # GPU layers
    context_window: int = 112000         # -c, contexto
    flash_attention: bool = True         # -fa
    flash_inference: bool = False        # -fit
    n_cpu_moe: int = 60                  # --n-cpu-moe
    threads_batch: int = 7               # --threads-batch
    threads: int = 8                     # --threads
    ubatch_size: int = 512               # --ubatch-size
    batch_size: int = 512                # --batch-size
    parallel: int = 1                    # --parallel
    temperature: float = 0.7             # --temp
    top_p: float = 0.8                   # --top-p
    top_k: int = 20                      # --top-k
    min_p: float = 0.1                   # --min-p
    repeat_penalty: float = 1.05         # --repeat-penalty
    cache_reuse: int = 256               # --cache-reuse
    cache_ram: int = -1                  # --cache-ram (auto)
    load_mode: str = "mlock"             # --load-mode
    spec_type: str = "draft-mtp"         # --spec-type
    spec_draft_n_max: int = 2            # --spec-draft-n-max
    moe_cache_slots: int = 0             # --moe-cache-slots (0 = flag no se pasa, cache off)
    sched_async_cpu: bool = True         # False → --no-sched-async-cpu

    # ── WHISPER (STT, CPU-only) ───────────────────
    whisper_bin: Path = field(default_factory=lambda: _p("~/codacus/whisper.cpp/build/bin/whisper-server"))
    whisper_model: Path = field(default_factory=lambda: _p("~/codacus/whisper.cpp/models/ggml-base.bin"))
    whisper_port: int = 8090
    whisper_log: Path = field(default_factory=lambda: _p("~/Rinthel-general/logs/whisper-server.log"))
    whisper_threads: int = 4

    # ── TTS (Piper, CPU-only) ─────────────────────
    tts_bin: Path = field(default_factory=lambda: _p("~/codacus/piper/piper/piper"))
    tts_server_script: Path = field(
        default_factory=lambda: _p("~/Rinthel-general/services/tts-piper/server.py")
    )
    tts_voice_es: Path = field(
        default_factory=lambda: _p("~/codacus/piper/voices/es_AR-daniela-high.onnx")
    )
    tts_voice_en: Path = field(
        default_factory=lambda: _p("~/codacus/piper/voices/en_US-hfc_female-medium.onnx")
    )
    tts_port: int = 8091
    tts_log: Path = field(default_factory=lambda: _p("~/Rinthel-general/logs/tts-piper.log"))

    def apply_env(self) -> None:
        """Aplica llama_env al entorno del proceso (llamar una vez al arrancar)."""
        os.environ.update(self.llama_env)
        self.log.parent.mkdir(parents=True, exist_ok=True)
        self._warn_missing_paths()

    def _warn_missing_paths(self) -> None:
        # Paths obligatorios para levantar llama-server: si no existen no
        # tiene sentido crashear el arranque de la TUI entera por eso — el
        # usuario puede querer usar solo MONITOR/LOGS sin bootear el modelo.
        # El fallo real ocurre (con mensaje claro) recién en phase_spawn_llama_server.
        for label, path in (("RINTHEL_LLAMA_BIN", self.bin), ("RINTHEL_MODEL_PATH", self.model)):
            if not path.exists():
                print(f"[rinthel] aviso: {label}={path} no existe todavía", file=sys.stderr)


def default_config() -> RinthelConfig:
    moe_cache_profile = _path_env(
        "RINTHEL_MOE_CACHE_PROFILE", "~/codacus/profiles/qwen3.6-merged.csv"
    )
    return RinthelConfig(
        llama_env={
            "GGML_CUDA_REGISTER_HOST": "1",
            "GGML_SCHED_PREFETCH_EXPERTS": "1",
            "GGML_MOE_CACHE_PROFILE": str(moe_cache_profile),
            "GGML_MOE_CACHE_SLOTS": "10",
        },
        bin=_path_env("RINTHEL_LLAMA_BIN", "~/codacus/llama.cpp/build-cuda/bin/llama-server"),
        model=_path_env("RINTHEL_MODEL_PATH", "~/llama.cpp/models/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf"),
        port=_int_env("RINTHEL_PORT", 8080),
        log=_path_env("RINTHEL_LOG_PATH", "~/Rinthel-general/logs/llama-server.log"),
        moe_trace_build=_path_env(
            "RINTHEL_MOE_TRACE_BUILD", "~/codacus/llama.cpp/build-cuda/bin/llama-moe-trace"
        ),
        moe_trace_out_dir=_path_env("RINTHEL_MOE_TRACE_OUT_DIR", "~/codacus/profiles"),
        moe_cache_profile=moe_cache_profile,
        understory_dir=_path_env("RINTHEL_UNDERSTORY_DIR", "~/understory-poc"),
        understory_port=_int_env("RINTHEL_UNDERSTORY_PORT", 3800),
        pithagoras_dir=_path_env("RINTHEL_PITHAGORAS_DIR", "~/pithagoras"),
        pithagoras_port=_int_env("RINTHEL_PITHAGORAS_PORT", 4100),
        llamacpp_repo_dir=_path_env("RINTHEL_LLAMACPP_REPO_DIR", "~/codacus/llama.cpp"),
        llamacpp_repo_url=_str_env(
            "RINTHEL_LLAMACPP_REPO_URL", "https://github.com/thecodacus/llama.cpp.git"
        ),
        model_download_url=_str_env(
            "RINTHEL_MODEL_DOWNLOAD_URL",
            "https://huggingface.co/unsloth/Qwen3.6-35B-A3B-MTP-GGUF/resolve/main/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf",
        ),
        pithagoras_repo_url=_str_env(
            "RINTHEL_PITHAGORAS_REPO_URL", "https://github.com/WilliamBarriga/pithagoras.git"
        ),
        workspaces_dir=_path_env("RINTHEL_WORKSPACES_DIR", "~"),
        pi_agent_dir=_path_env("RINTHEL_PI_AGENT_DIR", "~/.pi/agent"),
        ngl=_str_env("RINTHEL_NGL", "all"),
        context_window=_int_env("RINTHEL_CONTEXT_WINDOW", 112000),
        flash_attention=_bool_env("RINTHEL_FLASH_ATTENTION", True),
        flash_inference=_bool_env("RINTHEL_FLASH_INFERENCE", False),
        n_cpu_moe=_int_env("RINTHEL_N_CPU_MOE", 60),
        threads_batch=_int_env("RINTHEL_THREADS_BATCH", 7),
        threads=_int_env("RINTHEL_THREADS", 8),
        ubatch_size=_int_env("RINTHEL_UBATCH_SIZE", 512),
        batch_size=_int_env("RINTHEL_BATCH_SIZE", 512),
        parallel=_int_env("RINTHEL_PARALLEL", 1),
        temperature=_float_env("RINTHEL_TEMPERATURE", 0.7),
        top_p=_float_env("RINTHEL_TOP_P", 0.8),
        top_k=_int_env("RINTHEL_TOP_K", 20),
        min_p=_float_env("RINTHEL_MIN_P", 0.1),
        repeat_penalty=_float_env("RINTHEL_REPEAT_PENALTY", 1.05),
        cache_reuse=_int_env("RINTHEL_CACHE_REUSE", 256),
        cache_ram=_int_env("RINTHEL_CACHE_RAM", -1),
        load_mode=_str_env("RINTHEL_LOAD_MODE", "mlock"),
        spec_type=_str_env("RINTHEL_SPEC_TYPE", "draft-mtp"),
        spec_draft_n_max=_int_env("RINTHEL_SPEC_DRAFT_N_MAX", 2),
        moe_cache_slots=_int_env("RINTHEL_MOE_CACHE_SLOTS", 0),
        sched_async_cpu=_bool_env("RINTHEL_SCHED_ASYNC_CPU", True),
        whisper_bin=_path_env(
            "RINTHEL_WHISPER_BIN", "~/codacus/whisper.cpp/build/bin/whisper-server"
        ),
        whisper_model=_path_env(
            "RINTHEL_WHISPER_MODEL", "~/codacus/whisper.cpp/models/ggml-base.bin"
        ),
        whisper_port=_int_env("RINTHEL_WHISPER_PORT", 8090),
        whisper_log=_path_env("RINTHEL_WHISPER_LOG", "~/Rinthel-general/logs/whisper-server.log"),
        whisper_threads=_int_env("RINTHEL_WHISPER_THREADS", 4),
        tts_bin=_path_env("RINTHEL_TTS_BIN", "~/codacus/piper/piper/piper"),
        tts_server_script=_path_env(
            "RINTHEL_TTS_SERVER_SCRIPT", "~/Rinthel-general/services/tts-piper/server.py"
        ),
        tts_voice_es=_path_env(
            "RINTHEL_TTS_VOICE_ES", "~/codacus/piper/voices/es_AR-daniela-high.onnx"
        ),
        tts_voice_en=_path_env(
            "RINTHEL_TTS_VOICE_EN", "~/codacus/piper/voices/en_US-hfc_female-medium.onnx"
        ),
        tts_port=_int_env("RINTHEL_TTS_PORT", 8091),
        tts_log=_path_env("RINTHEL_TTS_LOG", "~/Rinthel-general/logs/tts-piper.log"),
    )


CONFIG = default_config()


# Toggle global de efectos visuales (glow, glitch, ripple, etc.) — apagable
# para terminales lentos o CI. Leído una vez al importar, como CONFIG.
EFFECTS_ENABLED = _bool_env("RINTHEL_EFFECTS", True)
