"""Única fuente de verdad para paths/puertos de infra.

Reemplaza ``nightcity/config/rinthel-env.sh``. A diferencia del bash, no hace
falta un patrón de "exportar todo arriba": las fases reciben ``cfg``
explícito como argumento (no leen el entorno global), así que no importa en
qué orden ni en qué proceso/subshell corran.

``RinthelConfig`` es composición de un sub-config por servicio
(``cfg.llama``, ``cfg.understory``, ``cfg.pithagoras``, ``cfg.moe``,
``cfg.install``) — cada uno con sus propios
campos, sin el prefijo repetido que tenían como campos sueltos del
dataclass monolítico anterior (``cfg.llama_port`` -> ``cfg.llama.port``).

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
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable

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
class Field:
    """Un campo cargable desde env var — vive junto al dataclass que
    describe, así que agregar/quitar un campo de un servicio es una sola
    línea en un solo lugar, en vez de tocar el parsing en ``default_config()``
    y por separado acordarse de sumarlo a los chequeos de ``validate()``.

    ``port``/``positive``/``exists`` etiquetan qué chequeo de ``validate()``
    le corresponde a este campo — ver ``_ENTRIES`` más abajo, que los agrega
    genéricamente en vez de 3 listas mantenidas a mano."""

    attr: str
    env: str
    kind: type
    default: Any
    port: bool = False
    positive: bool = False
    exists: bool = False
    # Categoría para agrupar visualmente en [N] CONFIGURAR (sesión 09 del
    # port-map) — "" para sub-configs con pocos campos que no lo necesitan
    # (understory/pithagoras/moe). Identificador plano (sin acentos) porque
    # cruza a JSON/Rust vía GET /config; el label mostrado es responsabilidad
    # del cliente.
    group: str = ""


_LOADERS: dict[type, Callable[[str, Any], Any]] = {
    Path: _path_env,
    int: _int_env,
    float: _float_env,
    bool: _bool_env,
    str: _str_env,
}

# Parsers de un valor crudo (string, ej. lo que llega en un override de
# POST /config) al tipo del campo — hermano de `_LOADERS`, que en cambio lee
# desde una env var. Mismo criterio de verdad que `_bool_env` para bool.
_PARSERS: dict[type, Callable[[str], Any]] = {
    Path: _p,
    int: int,
    float: float,
    bool: lambda raw: raw.strip().lower() in ("1", "on", "true", "yes"),
    str: lambda raw: raw,
}

# Nombre de tipo servido en GET /config (``kind``) para que el cliente sepa
# qué widget renderizar (checkbox vs. input) sin tener que conocer los tipos
# de Python — mismo criterio que "sin codegen" de ADR 0001, un dict chico en
# vez de una herramienta de schema.
KIND_NAMES: dict[type, str] = {
    Path: "path",
    int: "int",
    float: "float",
    bool: "bool",
    str: "str",
}


def _load(cls: type, fields: list[Field], **extra: Any) -> Any:
    """Instancia ``cls`` (un dataclass de config) leyendo cada ``Field`` de
    su env var — ``extra`` cubre los pocos campos que no salen 1:1 de una
    env var (ej. ``LlamaConfig.env``, sintetizado a partir de otros valores)."""
    kwargs = {f.attr: _LOADERS[f.kind](f.env, f.default) for f in fields}
    kwargs.update(extra)
    return cls(**kwargs)


@dataclass(frozen=True)
class LlamaConfig:
    bin: Path
    model: Path
    port: int
    log: Path
    env: dict[str, str]
    enabled: bool
    ngl: str
    context_window: int
    flash_attention: bool
    fit_to_memory: bool
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
    cache_type_k: str
    cache_type_v: str


# ``env`` queda afuera — se sintetiza a partir de ``moe_cache_profile``
# (ver ``default_config()``), no sale de una env var propia.
#
# Grupos revisados sesión 09 del port-map contra el `--help` real del build
# custom (`~/codacus/llama.cpp-perf-latest`, el que corre esta máquina, no
# el default de `bin` acá abajo): 26 de 27 campos (todos salvo `enabled`,
# que no es un flag) mapean 1:1 a flags vigentes de ese fork. Único
# desfasaje encontrado y corregido en esa
# sesión: este campo se llamaba `flash_inference`/`RINTHEL_FLASH_INFERENCE`
# pero arma `-fit` (`services.py::_llama_argv`), que es "ajustar args no
# seteados para entrar en memoria del device" — no tiene nada que ver con
# flash attention ni con inference. Renombrado a `fit_to_memory` para que la
# screen de settings no muestre un nombre engañoso.
LLAMA_FIELDS: list[Field] = [
    Field("bin", "RINTHEL_LLAMA_BIN", Path, "~/codacus/llama.cpp/build-cuda/bin/llama-server", exists=True, group="general"),
    Field("model", "RINTHEL_LLAMA_MODEL_PATH", Path, "~/llama.cpp/models/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf", exists=True, group="general"),
    Field("port", "RINTHEL_LLAMA_PORT", int, 8080, port=True, group="general"),
    Field("log", "RINTHEL_LLAMA_LOG_PATH", Path, "~/Rinthel-general/logs/llama-server.log", group="general"),
    Field("enabled", "RINTHEL_LLAMA_ENABLED", bool, True, group="general"),
    Field("ngl", "RINTHEL_NGL", str, "all", group="compute"),
    Field("context_window", "RINTHEL_CONTEXT_WINDOW", int, 112000, positive=True, group="general"),
    Field("flash_attention", "RINTHEL_FLASH_ATTENTION", bool, True, group="compute"),
    Field("fit_to_memory", "RINTHEL_FIT_TO_MEMORY", bool, False, group="compute"),
    Field("n_cpu_moe", "RINTHEL_N_CPU_MOE", int, 60, group="compute"),
    Field("threads_batch", "RINTHEL_THREADS_BATCH", int, 7, positive=True, group="compute"),
    Field("threads", "RINTHEL_THREADS", int, 8, positive=True, group="compute"),
    Field("ubatch_size", "RINTHEL_UBATCH_SIZE", int, 512, group="compute"),
    Field("batch_size", "RINTHEL_BATCH_SIZE", int, 512, group="compute"),
    Field("parallel", "RINTHEL_PARALLEL", int, 1, positive=True, group="compute"),
    Field("temperature", "RINTHEL_TEMPERATURE", float, 0.7, group="sampling"),
    Field("top_p", "RINTHEL_TOP_P", float, 0.8, group="sampling"),
    Field("top_k", "RINTHEL_TOP_K", int, 20, group="sampling"),
    Field("min_p", "RINTHEL_MIN_P", float, 0.1, group="sampling"),
    Field("repeat_penalty", "RINTHEL_REPEAT_PENALTY", float, 1.05, group="sampling"),
    Field("cache_reuse", "RINTHEL_CACHE_REUSE", int, 256, group="cache"),
    Field("cache_ram", "RINTHEL_CACHE_RAM", int, -1, group="cache"),
    Field("load_mode", "RINTHEL_LOAD_MODE", str, "mlock", group="general"),
    Field("spec_type", "RINTHEL_SPEC_TYPE", str, "draft-mtp", group="speculative"),
    Field("spec_draft_n_max", "RINTHEL_SPEC_DRAFT_N_MAX", int, 2, group="speculative"),
    Field("sched_async_cpu", "RINTHEL_SCHED_ASYNC_CPU", bool, True, group="compute"),
    Field("cache_type_k", "RINTHEL_CACHE_TYPE_K", str, "f16", group="cache"),
    Field("cache_type_v", "RINTHEL_CACHE_TYPE_V", str, "f16", group="cache"),
]


@dataclass(frozen=True)
class MoeConfig:
    trace_build: Path
    trace_out_dir: Path
    cache_profile: Path
    cache_slots: int


# ``cache_profile`` queda afuera — comparte valor con ``GGML_MOE_CACHE_PROFILE``
# de ``LlamaConfig.env``, se computa una sola vez en ``default_config()``.
MOE_FIELDS: list[Field] = [
    Field("trace_build", "RINTHEL_MOE_TRACE_BUILD", Path, "~/codacus/llama.cpp/build-cuda/bin/llama-moe-trace"),
    Field("trace_out_dir", "RINTHEL_MOE_TRACE_OUT_DIR", Path, "~/codacus/profiles"),
    Field("cache_slots", "RINTHEL_MOE_CACHE_SLOTS", int, 0),
]


@dataclass(frozen=True)
class UnderstoryConfig:
    dir: Path
    port: int
    enabled: bool


UNDERSTORY_FIELDS: list[Field] = [
    Field("dir", "RINTHEL_UNDERSTORY_DIR", Path, "~/understory-poc"),
    Field("port", "RINTHEL_UNDERSTORY_PORT", int, 3800, port=True),
    Field("enabled", "RINTHEL_UNDERSTORY_ENABLED", bool, True),
]


@dataclass(frozen=True)
class PithagorasConfig:
    dir: Path
    port: int
    enabled: bool


PITHAGORAS_FIELDS: list[Field] = [
    Field("dir", "RINTHEL_PITHAGORAS_DIR", Path, "~/pithagoras"),
    Field("port", "RINTHEL_PITHAGORAS_PORT", int, 4100, port=True),
    Field("enabled", "RINTHEL_PITHAGORAS_ENABLED", bool, True),
]


@dataclass(frozen=True)
class InstallConfig:
    llamacpp_repo_dir: Path
    llamacpp_repo_url: str
    model_download_url: str
    pithagoras_repo_url: str
    workspaces_dir: Path
    pi_agent_dir: Path


INSTALL_FIELDS: list[Field] = [
    Field("llamacpp_repo_dir", "RINTHEL_LLAMACPP_REPO_DIR", Path, "~/codacus/llama.cpp"),
    Field("llamacpp_repo_url", "RINTHEL_LLAMACPP_REPO_URL", str, "https://github.com/thecodacus/llama.cpp.git"),
    Field(
        "model_download_url",
        "RINTHEL_MODEL_DOWNLOAD_URL",
        str,
        "https://huggingface.co/unsloth/Qwen3.6-35B-A3B-MTP-GGUF/resolve/main/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf",
    ),
    Field("pithagoras_repo_url", "RINTHEL_PITHAGORAS_REPO_URL", str, "https://github.com/WilliamBarriga/pithagoras.git"),
    Field("workspaces_dir", "RINTHEL_WORKSPACES_DIR", Path, "~"),
    Field("pi_agent_dir", "RINTHEL_PI_AGENT_DIR", Path, "~/.pi/agent"),
]


# Un solo lugar que empareja cada sub-config con su tabla de campos —
# ``RinthelConfig.validate()`` deriva los 3 chequeos (puertos, positivos,
# paths) de acá en vez de mantener 3 listas a mano por separado. Agregar un
# servicio nuevo es sumar una línea acá, no 3 en 3 lugares distintos.
# ``attr`` dobla como prefijo de los mensajes de error/warning (ej.
# "llama.port=...") porque coincide 1:1 con el nombre del sub-config en
# RinthelConfig — no hay caso hoy donde difieran.
_ENTRIES: list[tuple[str, list[Field]]] = [
    ("llama", LLAMA_FIELDS),
    ("moe", MOE_FIELDS),
    ("understory", UNDERSTORY_FIELDS),
    ("pithagoras", PITHAGORAS_FIELDS),
    ("install", INSTALL_FIELDS),
]


class ConfigError(Exception):
    """Config inválida de forma tal que ninguna fase puede andar bien —
    se levanta antes de arrancar nada (ver ``RinthelConfig.validate``)."""


@dataclass(frozen=True)
class RinthelConfig:
    llama: LlamaConfig
    moe: MoeConfig
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
        seen_ports: dict[int, str] = {}
        for attr, fields in _ENTRIES:
            sub = getattr(self, attr)
            for f in fields:
                if not f.port:
                    continue
                name = f"{attr}.{f.attr}"
                port = getattr(sub, f.attr)
                if not (1 <= port <= 65535):
                    errors.append(f"{name}={port} fuera de rango 1-65535")
                elif port in seen_ports:
                    errors.append(f"{name}={port} choca con {seen_ports[port]}")
                else:
                    seen_ports[port] = name

        for attr, fields in _ENTRIES:
            sub = getattr(self, attr)
            for f in fields:
                if f.positive and getattr(sub, f.attr) <= 0:
                    errors.append(f"{attr}.{f.attr}={getattr(sub, f.attr)} debe ser > 0")

        if errors:
            raise ConfigError("; ".join(errors))

        warnings: list[str] = []
        for attr, fields in _ENTRIES:
            sub = getattr(self, attr)
            for f in fields:
                if not f.exists:
                    continue
                path = getattr(sub, f.attr)
                if not path.exists():
                    warnings.append(f"{f.env}={path} no existe todavía")
        return warnings


# ── Lectura/escritura genérica de campos — usado por GET/POST /config
# (sesión 09 del port-map, amendment de docs/adr/0001) y por [N] CONFIGURAR
# del lado Textual (rinthel_tui/tui/screens/settings.py). Vive acá y no en
# la screen porque el daemon (no Textual) también lo necesita ahora que es
# dueño de la config — ver Decision Q1 de esa sesión. ──────────────────────


def stringify(value: object) -> str:
    """Misma representación de texto que terminaría en el .env — bool va
    como "true"/"false" (lo que ``_bool_env``/``_PARSERS[bool]`` aceptan),
    no "True"/"False"."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def diff_overrides(cfg: RinthelConfig, edits: dict[str, str]) -> dict[str, str]:
    """De todo lo tocado (``edits``: env var -> valor nuevo como string),
    devuelve solo lo que de verdad difiere del valor actual en ``cfg`` — lo
    mínimo que hay que escribir en el .env."""
    overrides: dict[str, str] = {}
    for attr, fields in _ENTRIES:
        sub = getattr(cfg, attr)
        for f in fields:
            if f.env not in edits:
                continue
            if edits[f.env] != stringify(getattr(sub, f.attr)):
                overrides[f.env] = edits[f.env]
    return overrides


def with_overrides(cfg: RinthelConfig, overrides: dict[str, str]) -> RinthelConfig:
    """Aplica ``overrides`` (env var -> string, mismo shape que
    ``diff_overrides``/``update_env_file``) sobre una copia de ``cfg`` sin
    tocar el .env — usado por ``POST /config`` para validar el estado
    resultante (``RinthelConfig.validate()``) antes de escribir de verdad."""
    kwargs: dict[str, Any] = {}
    for attr, fields in _ENTRIES:
        sub = getattr(cfg, attr)
        changes = {f.attr: _PARSERS[f.kind](overrides[f.env]) for f in fields if f.env in overrides}
        kwargs[attr] = replace(sub, **changes) if changes else sub
    return replace(cfg, **kwargs)


def default_config() -> RinthelConfig:
    # Computado antes de los _load() de LLAMA_FIELDS/MOE_FIELDS -- lo comparten
    # llama.env["GGML_MOE_CACHE_PROFILE"] y moe.cache_profile, ninguno de los
    # dos lo carga por su cuenta.
    moe_cache_profile = _path_env(
        "RINTHEL_MOE_CACHE_PROFILE", "~/codacus/profiles/qwen3.6-merged.csv"
    )

    llama = _load(
        LlamaConfig,
        LLAMA_FIELDS,
        env={
            "GGML_CUDA_REGISTER_HOST": "1",
            "GGML_SCHED_PREFETCH_EXPERTS": "1",
            "GGML_MOE_CACHE_PROFILE": str(moe_cache_profile),
            "GGML_MOE_CACHE_SLOTS": "10",
        },
    )
    moe = _load(MoeConfig, MOE_FIELDS, cache_profile=moe_cache_profile)
    understory = _load(UnderstoryConfig, UNDERSTORY_FIELDS)
    pithagoras = _load(PithagorasConfig, PITHAGORAS_FIELDS)
    install = _load(InstallConfig, INSTALL_FIELDS)

    return RinthelConfig(
        llama=llama, moe=moe,
        understory=understory, pithagoras=pithagoras, install=install,
    )


CONFIG = default_config()


# Toggle global de efectos visuales (glow, glitch, ripple, etc.) — apagable
# para terminales lentos o CI. Leído una vez al importar, como CONFIG.
EFFECTS_ENABLED = _bool_env("RINTHEL_EFFECTS", True)
