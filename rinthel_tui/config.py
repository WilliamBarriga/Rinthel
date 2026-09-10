"""Única fuente de verdad para paths/puertos de infra.

Reemplaza ``nightcity/config/rinthel-env.sh``. A diferencia del bash, no hace
falta un patrón de "exportar todo arriba": las fases reciben ``cfg``
explícito como argumento (no leen el entorno global), así que no importa en
qué orden ni en qué proceso/subshell corran.

``RinthelConfig`` es composición de un sub-config por servicio
(``cfg.llama``, ``cfg.whisper``, ``cfg.tts``, ``cfg.understory``,
``cfg.pithagoras``, ``cfg.moe``, ``cfg.install``) — cada uno con sus propios
campos, sin el prefijo repetido que tenían como campos sueltos del
dataclass monolítico anterior (``cfg.whisper_port`` -> ``cfg.whisper.port``).

Todo campo puede overridearse con una var de entorno ``RINTHEL_*`` (ver
``.env.example``) — los nombres de esas vars NO cambiaron con este split,
salvo el caso especial de llama-server, que antes no tenía prefijo
(``RINTHEL_PORT``/``RINTHEL_MODEL_PATH``/``RINTHEL_LOG_PATH``) y ahora es
consistente con el resto de los servicios (``RINTHEL_LLAMA_PORT``/
``RINTHEL_LLAMA_MODEL_PATH``/``RINTHEL_LLAMA_LOG_PATH``).

Si existe un ``.env`` en la raíz de este repo, se carga automáticamente vía
``python-dotenv`` antes de leer el entorno — sin ``.env``, los defaults de
``default_config()`` quedan idénticos al comportamiento anterior.
"""

import os
import sys
from dataclasses import dataclass
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
class LlamaConfig:
    bin: Path
    model: Path
    port: int
    log: Path
    env: dict[str, str]
    ngl: str
    context_window: int
    flash_attention: bool
    flash_inference: bool
    n_cpu_moe: int
    threads_batch: int
    threads: int
    ubatch_size: int
    batch_size: int
    parallel: int
    temperature: float
    top_p: float
    top_k: int
    min_p: float
    repeat_penalty: float
    cache_reuse: int
    cache_ram: int
    load_mode: str
    spec_type: str
    spec_draft_n_max: int
    sched_async_cpu: bool


@dataclass(frozen=True)
class MoeConfig:
    trace_build: Path
    trace_out_dir: Path
    cache_profile: Path
    cache_slots: int


@dataclass(frozen=True)
class WhisperConfig:
    bin: Path
    model: Path
    port: int
    log: Path
    threads: int


@dataclass(frozen=True)
class TTSConfig:
    bin: Path
    server_script: Path
    voice_es: Path
    voice_en: Path
    port: int
    log: Path


@dataclass(frozen=True)
class UnderstoryConfig:
    dir: Path
    port: int


@dataclass(frozen=True)
class PithagorasConfig:
    dir: Path
    port: int


@dataclass(frozen=True)
class InstallConfig:
    llamacpp_repo_dir: Path
    llamacpp_repo_url: str
    model_download_url: str
    pithagoras_repo_url: str
    workspaces_dir: Path
    pi_agent_dir: Path


class ConfigError(Exception):
    """Config inválida de forma tal que ninguna fase puede andar bien —
    se levanta antes de arrancar nada (ver ``RinthelConfig.validate``)."""


@dataclass(frozen=True)
class RinthelConfig:
    llama: LlamaConfig
    moe: MoeConfig
    whisper: WhisperConfig
    tts: TTSConfig
    understory: UnderstoryConfig
    pithagoras: PithagorasConfig
    install: InstallConfig

    def apply_env(self) -> None:
        """Aplica llama.env al entorno del proceso y valida la config
        (llamar una vez al arrancar). Levanta ConfigError si algo rompe
        seguro (puertos duplicados/fuera de rango, numéricos inválidos);
        imprime a stderr los warnings de paths que todavía no existen."""
        os.environ.update(self.llama.env)
        self.llama.log.parent.mkdir(parents=True, exist_ok=True)
        for warning in self.validate():
            print(f"[rinthel] aviso: {warning}", file=sys.stderr)

    def validate(self) -> list[str]:
        """Devuelve warnings de paths que no existen todavía (no bloquean:
        el usuario puede querer usar solo MONITOR/LOGS sin bootear nada, y
        el fallo real ocurre con mensaje claro recién en phase_spawn).
        Levanta ConfigError si encuentra algo que garantiza romper cualquier
        fase que corra (puertos duplicados/inválidos, numéricos ≤0) — el
        split en sub-configs hizo fácil, por ejemplo, que dos servicios
        terminen apuntando al mismo puerto sin que nadie lo note hasta que
        uno de los dos falla a "levantar" en silencio."""
        errors: list[str] = []

        ports = {
            "llama.port": self.llama.port,
            "whisper.port": self.whisper.port,
            "tts.port": self.tts.port,
            "understory.port": self.understory.port,
            "pithagoras.port": self.pithagoras.port,
        }
        seen: dict[int, str] = {}
        for name, port in ports.items():
            if not (1 <= port <= 65535):
                errors.append(f"{name}={port} fuera de rango 1-65535")
                continue
            if port in seen:
                errors.append(f"{name}={port} choca con {seen[port]}")
            else:
                seen[port] = name

        for name, value in (
            ("llama.threads", self.llama.threads),
            ("llama.threads_batch", self.llama.threads_batch),
            ("llama.context_window", self.llama.context_window),
            ("llama.parallel", self.llama.parallel),
            ("whisper.threads", self.whisper.threads),
        ):
            if value <= 0:
                errors.append(f"{name}={value} debe ser > 0")

        if errors:
            raise ConfigError("; ".join(errors))

        warnings: list[str] = []
        for label, path in (
            ("RINTHEL_LLAMA_BIN", self.llama.bin),
            ("RINTHEL_LLAMA_MODEL_PATH", self.llama.model),
            ("RINTHEL_WHISPER_BIN", self.whisper.bin),
            ("RINTHEL_WHISPER_MODEL", self.whisper.model),
            ("RINTHEL_TTS_BIN", self.tts.bin),
            ("RINTHEL_TTS_SERVER_SCRIPT", self.tts.server_script),
            ("RINTHEL_TTS_VOICE_ES", self.tts.voice_es),
            ("RINTHEL_TTS_VOICE_EN", self.tts.voice_en),
        ):
            if not path.exists():
                warnings.append(f"{label}={path} no existe todavía")
        return warnings


def default_config() -> RinthelConfig:
    moe_cache_profile = _path_env(
        "RINTHEL_MOE_CACHE_PROFILE", "~/codacus/profiles/qwen3.6-merged.csv"
    )

    llama = LlamaConfig(
        bin=_path_env("RINTHEL_LLAMA_BIN", "~/codacus/llama.cpp/build-cuda/bin/llama-server"),
        model=_path_env("RINTHEL_LLAMA_MODEL_PATH", "~/llama.cpp/models/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf"),
        port=_int_env("RINTHEL_LLAMA_PORT", 8080),
        log=_path_env("RINTHEL_LLAMA_LOG_PATH", "~/Rinthel-general/logs/llama-server.log"),
        env={
            "GGML_CUDA_REGISTER_HOST": "1",
            "GGML_SCHED_PREFETCH_EXPERTS": "1",
            "GGML_MOE_CACHE_PROFILE": str(moe_cache_profile),
            "GGML_MOE_CACHE_SLOTS": "10",
        },
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
        sched_async_cpu=_bool_env("RINTHEL_SCHED_ASYNC_CPU", True),
    )

    moe = MoeConfig(
        trace_build=_path_env(
            "RINTHEL_MOE_TRACE_BUILD", "~/codacus/llama.cpp/build-cuda/bin/llama-moe-trace"
        ),
        trace_out_dir=_path_env("RINTHEL_MOE_TRACE_OUT_DIR", "~/codacus/profiles"),
        cache_profile=moe_cache_profile,
        cache_slots=_int_env("RINTHEL_MOE_CACHE_SLOTS", 0),
    )

    whisper = WhisperConfig(
        bin=_path_env("RINTHEL_WHISPER_BIN", "~/codacus/whisper.cpp/build/bin/whisper-server"),
        model=_path_env("RINTHEL_WHISPER_MODEL", "~/codacus/whisper.cpp/models/ggml-base.bin"),
        port=_int_env("RINTHEL_WHISPER_PORT", 8090),
        log=_path_env("RINTHEL_WHISPER_LOG", "~/Rinthel-general/logs/whisper-server.log"),
        threads=_int_env("RINTHEL_WHISPER_THREADS", 4),
    )

    tts = TTSConfig(
        bin=_path_env("RINTHEL_TTS_BIN", "~/codacus/piper/piper/piper"),
        server_script=_path_env(
            "RINTHEL_TTS_SERVER_SCRIPT", "~/Rinthel-general/services/tts-piper/server.py"
        ),
        voice_es=_path_env("RINTHEL_TTS_VOICE_ES", "~/codacus/piper/voices/es_AR-daniela-high.onnx"),
        voice_en=_path_env("RINTHEL_TTS_VOICE_EN", "~/codacus/piper/voices/en_US-hfc_female-medium.onnx"),
        port=_int_env("RINTHEL_TTS_PORT", 8091),
        log=_path_env("RINTHEL_TTS_LOG", "~/Rinthel-general/logs/tts-piper.log"),
    )

    understory = UnderstoryConfig(
        dir=_path_env("RINTHEL_UNDERSTORY_DIR", "~/understory-poc"),
        port=_int_env("RINTHEL_UNDERSTORY_PORT", 3800),
    )

    pithagoras = PithagorasConfig(
        dir=_path_env("RINTHEL_PITHAGORAS_DIR", "~/pithagoras"),
        port=_int_env("RINTHEL_PITHAGORAS_PORT", 4100),
    )

    install = InstallConfig(
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
    )

    return RinthelConfig(
        llama=llama, moe=moe, whisper=whisper, tts=tts,
        understory=understory, pithagoras=pithagoras, install=install,
    )


CONFIG = default_config()


# Toggle global de efectos visuales (glow, glitch, ripple, etc.) — apagable
# para terminales lentos o CI. Leído una vez al importar, como CONFIG.
EFFECTS_ENABLED = _bool_env("RINTHEL_EFFECTS", True)
