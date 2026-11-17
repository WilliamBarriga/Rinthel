"""Única fuente de verdad para paths/puertos de infra.

Reemplaza ``nightcity/config/rinthel-env.sh``. A diferencia del bash, no hace
falta un patrón de "exportar todo arriba": las fases reciben ``cfg``
explícito como argumento (no leen el entorno global), así que no importa en
qué orden ni en qué proceso/subshell corran.

``RinthelConfig`` es composición de un sub-config por servicio
(``cfg.llama``, ``cfg.understory``, ``cfg.deck``, ``cfg.moe``,
``cfg.install``) — cada uno con sus propios
campos, sin el prefijo repetido que tenían como campos sueltos del
dataclass monolítico anterior (``cfg.llama_port`` -> ``cfg.llama.port``).

Todo campo puede overridearse con una var de entorno ``RINTHEL_*`` (ver
``.env.example``) — los nombres de esas vars NO cambiaron con este split,
salvo el caso especial de llama-server, que antes no tenía prefijo propio y
ahora es consistente con el resto de los servicios (``RINTHEL_LLAMA_PORT``/
``RINTHEL_LLAMA_MODEL_PATH``/``RINTHEL_LLAMA_LOG_PATH``).

``default_config(instance)`` lee el ``.env`` de la Instance (ver
``instance.py``) directo del archivo, sin tocar ``os.environ`` — las
``RINTHEL_*`` del shell ganan sobre el archivo.
"""

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

from rinthel_tui.instance import Instance
from rinthel_tui.lifecycle.domain.types import Platform
from rinthel_tui.models.adapters.json_catalog import JsonCatalog
from rinthel_tui.models.adapters.toml_active import TomlActiveModels
from rinthel_tui.models.domain.models import resolve
from rinthel_tui.models.domain.types import DEFAULT_REASONING_FORMAT, LocalModel


def _p(path: str) -> Path:
    return Path(path).expanduser()


def _str_env(name: str, default: str, env: Mapping[str, str] | None = None) -> str:
    return (os.environ if env is None else env).get(name, default)


def _path_env(name: str, default: str, env: Mapping[str, str] | None = None) -> Path:
    return _p((os.environ if env is None else env).get(name, default))


def _int_env(name: str, default: int, env: Mapping[str, str] | None = None) -> int:
    val = (os.environ if env is None else env).get(name, "").strip()
    return int(val) if val else default


def _float_env(name: str, default: float, env: Mapping[str, str] | None = None) -> float:
    val = (os.environ if env is None else env).get(name, "").strip()
    return float(val) if val else default


def _bool_env(name: str, default: bool, env: Mapping[str, str] | None = None) -> bool:
    val = (os.environ if env is None else env).get(name, "").strip().lower()
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
    # Categoría para agrupar visualmente en [N] CONFIGURAR — "" para
    # sub-configs con pocos campos que no lo necesitan (understory/
    # deck/moe). Identificador plano (sin acentos) porque cruza a
    # JSON/Rust vía GET /config; el label mostrado es responsabilidad del
    # cliente.
    group: str = ""


_LOADERS: dict[type, Callable[[str, Any, Mapping[str, str]], Any]] = {
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


def _load(
    cls: type,
    fields: list[Field],
    source: Mapping[str, str],
    instance: Instance,
    *,
    defaults: dict[str, Any] | None = None,
) -> Any:
    """Instancia ``cls`` (un dataclass de config) leyendo cada ``Field`` de
    ``source``. ``defaults`` pisa el default de algunos campos (el Validated profile de
    una Platform). Un ``default`` callable es un default de layout: se
    resuelve contra la ``instance`` (ej. ``understory.dir``)."""
    defaults = defaults or {}

    def default_of(f: Field) -> Any:
        value = defaults.get(f.attr, f.default)
        return value(instance) if callable(value) else value

    return cls(**{f.attr: _LOADERS[f.kind](f.env, default_of(f), source) for f in fields})


_LOCAL_MODEL_HINT = "es del Local model: editá models.local.json y elegí el activo con «models use <id>»"

# Variables del fork thecodacus/llama.cpp que llama.cpp upstream no tiene: un
# .env viejo las puede seguir trayendo y se ignoran en silencio.
_LEGACY_ENV: dict[str, str] = {
    "RINTHEL_MOE_CACHE_SLOTS": "usá RINTHEL_MOE_CACHE_MIB (--moe-cache-mib de upstream)",
    "RINTHEL_MOE_CACHE_PROFILE": "el perfil de ruteo MoE ya no existe en upstream",
    "RINTHEL_MOE_TRACE_BUILD": "llama-moe-trace ya no existe en upstream",
    "RINTHEL_MOE_TRACE_OUT_DIR": "llama-moe-trace ya no existe en upstream",
    "RINTHEL_SCHED_ASYNC_CPU": "--no-sched-async-cpu ya no existe en upstream",
    # Lo que ahora es de cada Local model (catálogo ``models.local.json`` y
    # ``[models]`` de ``data/instance.toml``), no del ``.env``.
    "RINTHEL_LLAMA_MODEL_PATH": _LOCAL_MODEL_HINT,
    "RINTHEL_CONTEXT_WINDOW": _LOCAL_MODEL_HINT,
    "RINTHEL_LLAMA_MMPROJ_PATH": _LOCAL_MODEL_HINT,
    "RINTHEL_LLAMA_MMPROJ_ENABLED": _LOCAL_MODEL_HINT,
    "RINTHEL_MTP_ENABLED": _LOCAL_MODEL_HINT,
    "RINTHEL_MODEL_DOWNLOAD_URL": "INSTALL descarga el modelo por defecto del Validated profile",
}


@dataclass(frozen=True)
class LlamaConfig:
    bin: Path
    port: int
    log: Path
    enabled: bool
    ngl: str
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
    # El modo de MTP (speculative decoding) cuando el Local model activo lo
    # prende (``mtp`` en su entrada del catálogo); con ``mtp`` apagado el
    # argv arranca con ``--spec-type none`` sin mirar este valor (ver
    # ``lifecycle/services.py::_llama_argv``).
    spec_type: str
    spec_draft_n_max: int
    cache_type_k: str
    cache_type_v: str


# `fit_to_memory` arma el flag `-fit` (`services.py::_llama_argv`), que
# ajusta los args no seteados para entrar en memoria del device — no tiene
# relación con flash attention pese a lo que sugeriría un nombre distinto.
LLAMA_FIELDS: list[Field] = [
    Field("bin", "RINTHEL_LLAMA_BIN", Path, "~/llama.cpp/src/build-cuda/bin/llama-server", exists=True, group="general"),
    Field("port", "RINTHEL_LLAMA_PORT", int, 8080, port=True, group="general"),
    Field("log", "RINTHEL_LLAMA_LOG_PATH", Path, lambda i: str(i.logs_dir / "llama-server.log"), group="general"),
    Field("enabled", "RINTHEL_LLAMA_ENABLED", bool, True, group="general"),
    Field("ngl", "RINTHEL_NGL", str, "all", group="compute"),
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
    Field("cache_type_k", "RINTHEL_CACHE_TYPE_K", str, "f16", group="cache"),
    Field("cache_type_v", "RINTHEL_CACHE_TYPE_V", str, "f16", group="cache"),
]

@dataclass(frozen=True)
class DefaultModel:
    """El Local model que INSTALL descarga y deja activo: la entrada inicial
    del catálogo, con la ventana de contexto medida para la Platform."""

    id: str
    name: str
    file: str
    url: str
    context_window: int
    reasoning_format: str = DEFAULT_REASONING_FORMAT


@dataclass(frozen=True)
class ValidatedProfile:
    """El Validated profile de una Platform (ver GLOSSARY.md), en un solo
    lugar: ``llama`` pisa el default de los ``LLAMA_FIELDS`` de hardware
    (una variable explícita del ``.env`` o del shell sigue ganando) y
    ``model`` es el Local model por defecto. Cambiar cualquiera de los dos
    cambia el argv de ``llama-server``, y eso pide un benchmark nuevo
    (``docs/05-windows-validation.md``)."""

    llama: dict[str, Any]
    model: DefaultModel


_QWEN = "Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf"


def _qwen(context_window: int) -> DefaultModel:
    return DefaultModel(
        id="qwen3.6-35b-a3b",
        name="Qwen3.6 35B A3B",
        file=_QWEN,
        url=f"https://huggingface.co/unsloth/Qwen3.6-35B-A3B-MTP-GGUF/resolve/main/{_QWEN}",
        context_window=context_window,
    )


VALIDATED_PROFILES: dict[Platform, ValidatedProfile] = {
    # Los defaults de LLAMA_FIELDS son los de Linux.
    "linux": ValidatedProfile(llama={}, model=_qwen(112000)),
    # Medido en la máquina de referencia (docs/05-windows-validation.md).
    "windows": ValidatedProfile(
        llama={
            "n_cpu_moe": 34,
            "ubatch_size": 2048,
            "batch_size": 2048,
            "spec_type": "none",
            "cache_type_k": "q8_0",
            "cache_type_v": "q8_0",
        },
        model=_qwen(65536),
    ),
}


@dataclass(frozen=True)
class MoeConfig:
    cache_mib: int


# ``--moe-cache-mib`` de llama.cpp upstream: MiB de VRAM para cachear los
# expertos MoE que viven en CPU. 0 = deshabilitado (default de upstream).
MOE_FIELDS: list[Field] = [
    Field("cache_mib", "RINTHEL_MOE_CACHE_MIB", int, 0),
]


@dataclass(frozen=True)
class UnderstoryConfig:
    dir: Path
    port: int
    enabled: bool


UNDERSTORY_FIELDS: list[Field] = [
    # Subtree del monorepo. Estado real (bundle) vive en la raíz de la
    # Instance, en data/understory; ver docker-compose.yaml de la raíz.
    Field("dir", "RINTHEL_UNDERSTORY_DIR", Path, lambda i: str(i.understory_dir)),
    Field("port", "RINTHEL_UNDERSTORY_PORT", int, 3800, port=True),
    Field("enabled", "RINTHEL_UNDERSTORY_ENABLED", bool, True),
]


@dataclass(frozen=True)
class DeckConfig:
    """Lo que el daemon necesita saber de Deck. ``host_address`` es cómo Deck
    alcanza el host desde su contenedor: el daemon arma con ella toda URL que
    le entrega (la ruta de llama, voz, hostexecd); Deck nunca las reescribe."""

    host_address: str
    dir: Path
    port: int
    enabled: bool


DECK_FIELDS: list[Field] = [
    Field("host_address", "RINTHEL_DECK_HOST_ADDRESS", str, "127.0.0.1"),
    # Subtree del monorepo. Estado real (deck.db, home de pi) vive en la raíz
    # de la Instance, en data/deck.
    Field("dir", "RINTHEL_DECK_DIR", Path, lambda i: str(i.deck_dir)),
    Field("port", "RINTHEL_DECK_PORT", int, 4100, port=True),
    Field("enabled", "RINTHEL_DECK_ENABLED", bool, True),
]

# Default por Platform: en Linux el contenedor comparte la red del host;
# Docker Desktop (Windows) llega al host por su nombre reservado.
_DECK_DEFAULTS: dict[Platform, dict[str, Any]] = {
    "linux": {},
    "windows": {"host_address": "host.docker.internal"},
}


@dataclass(frozen=True)
class HostExecConfig:
    """``hostexecd``, the daemon-managed process that runs an admin's commands
    on the host (Linux only). ``token`` is the one INSTALL writes in the root
    ``.env``; like ``Secrets`` it never goes through ``GET /config``."""

    port: int
    enabled: bool
    token: str = ""


HOSTEXECD_FIELDS: list[Field] = [
    Field("port", "RINTHEL_HOSTEXECD_PORT", int, 8766, port=True),
    Field("enabled", "RINTHEL_HOSTEXECD_ENABLED", bool, True),
]

# Host exec is Linux only: off by default on Windows, and never started there
# whatever the ``.env`` says (``HOSTEXECD_SERVICE.enabled_of``).
_HOSTEXECD_DEFAULTS: dict[Platform, dict[str, Any]] = {
    "linux": {},
    "windows": {"enabled": False},
}

HOSTEXECD_TOKEN_ENV = "RINTHEL_HOSTEXECD_TOKEN"


@dataclass(frozen=True)
class Secrets:
    """Los secretos de la Instance que el daemon lee. Van aparte de
    ``_ENTRIES``: ``GET /config`` nunca los muestra. ``service`` es el que
    exige la policy ``service`` (la TUI); ``panel`` firma los Panel tokens.
    Sin default real: un secreto vacío no deja pasar a nadie. Los genera
    INSTALL (``phase_install_instance_secrets``) y el boot (``service``)."""

    service: str
    panel: str


SECRET_ENVS: dict[str, str] = {
    "service": "RINTHEL_SERVICE_SECRET",
    "panel": "RINTHEL_PANEL_SECRET",
}


@dataclass(frozen=True)
class IdentityConfig:
    """Panel token lifetimes. Out of ``_ENTRIES`` like ``Secrets``: they are
    set in the ``.env``, not from ``[N] CONFIGURAR``."""

    access_ttl_seconds: int = 86_400  # 1 day
    refresh_ttl_seconds: int = 2_592_000  # 30 days


IDENTITY_FIELDS: list[Field] = [
    Field("access_ttl_seconds", "RINTHEL_IDENTITY_ACCESS_TTL", int, 86_400, positive=True),
    Field("refresh_ttl_seconds", "RINTHEL_IDENTITY_REFRESH_TTL", int, 2_592_000, positive=True),
]


@dataclass(frozen=True)
class InstallConfig:
    llamacpp_repo_dir: Path
    llamacpp_repo_url: str
    models_dir: Path


INSTALL_FIELDS: list[Field] = [
    Field("llamacpp_repo_dir", "RINTHEL_LLAMACPP_REPO_DIR", Path, "~/llama.cpp/src"),
    Field("llamacpp_repo_url", "RINTHEL_LLAMACPP_REPO_URL", str, "https://github.com/ggml-org/llama.cpp.git"),
    # Donde INSTALL baja el GGUF del Local model por defecto (fuera del repo).
    Field("models_dir", "RINTHEL_MODELS_DIR", Path, "~/llama.cpp/models"),
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
    ("deck", DECK_FIELDS),
    ("hostexecd", HOSTEXECD_FIELDS),
    ("install", INSTALL_FIELDS),
]


class ConfigError(Exception):
    """Config inválida de forma tal que ninguna fase puede andar bien —
    se levanta antes de arrancar nada (ver ``RinthelConfig.validate``)."""


@dataclass(frozen=True)
class RinthelConfig:
    instance: Instance
    llama: LlamaConfig
    moe: MoeConfig
    understory: UnderstoryConfig
    deck: DeckConfig
    install: InstallConfig
    hostexecd: HostExecConfig = HostExecConfig(8766, True)
    secrets: Secrets = Secrets("", "")
    identity: IdentityConfig = IdentityConfig()
    # Las variables legacy presentes al construir el cfg (shell o ``.env``).
    legacy_env: tuple[str, ...] = ()
    platform: Platform = "linux"
    # El Local model activo de ``llm`` que llama-server sirve (o va a servir
    # en el próximo boot). ``None``: no hay uno usable y llama no arranca;
    # ``model_warning`` dice por qué.
    local_model: LocalModel | None = None
    model_warning: str | None = None

    @property
    def profile(self) -> ValidatedProfile:
        return VALIDATED_PROFILES[self.platform]

    def model_llama(self) -> LlamaConfig:
        """``llama`` con los overrides propios del Local model activo (solo
        los de su lista blanca: sampling y speculative decoding)."""
        if self.local_model is None or not self.local_model.overrides:
            return self.llama
        kinds = {f.attr: f.kind for f in LLAMA_FIELDS}
        return replace(
            self.llama,
            **{attr: _PARSERS[kinds[attr]](str(v)) for attr, v in self.local_model.overrides.items()},
        )

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
        warnings.extend(f"{name} ya no se usa: {_LEGACY_ENV[name]}" for name in self.legacy_env)
        if self.model_warning:
            warnings.append(self.model_warning)
        warnings.extend(self._mtp_warnings())
        return warnings

    def _mtp_warnings(self) -> list[str]:
        """Avisos de los combos MTP que la investigación de
        ``test-tarkAIrk`` dejó medidos como inseguros (VRAM) o directamente
        ignorados/rotos por ``llama.cpp``. No son errores: se puede querer
        guardar la config igual (p. ej. encender MTP con batch 2048 a sabiendas
        de que hay que bajarlo si revienta), así que van como warning — llegan
        al cliente como ``warnings`` del ``POST /config``, que es donde el TUI
        los pinta en la barra de estado de ``[N] CONFIGURAR``.

        Fuentes: ``test-tarkAIrk/logs/08`` (OOM de MTP, ~650 MiB de compute
        buffer extra), ``logs/27`` (MTP + batch 2048 = 48 MiB libres, reproduce
        el OOM) y ``handoff/03`` (MTP no soporta ``--parallel`` > 1 ni
        ``--mmproj``)."""
        model = self.local_model
        if model is None or not model.mtp:
            return []
        llama = self.model_llama()
        out: list[str] = []
        if max(llama.batch_size, llama.ubatch_size) > 1024:
            out.append(
                f"MTP + batch/ubatch {llama.batch_size}/{llama.ubatch_size}: "
                "crashea con CUDA OOM en el uso real de esta GPU de 8GB (48 MiB libres, "
                "test-tarkAIrk/logs/27) — si el server muere en el primer request, bajá "
                "RINTHEL_BATCH_SIZE/RINTHEL_UBATCH_SIZE a 1024 o 512 desde [N] CONFIGURAR > CÓMPUTO"
            )
        if llama.parallel > 1:
            out.append(
                f"MTP + RINTHEL_PARALLEL={llama.parallel}: llama.cpp no soporta MTP con "
                "--parallel > 1 (test-tarkAIrk/handoff/03) — bajá parallel a 1 con MTP prendido"
            )
        if model.mmproj is not None:
            out.append(
                "MTP + visión (--mmproj): llama.cpp no soporta MTP con --mmproj — el flag queda "
                "omitido del argv mientras MTP esté prendido (el catálogo no se toca)"
            )
        if llama.spec_type in ("", "none"):
            out.append(
                f"mtp=true en {model.id} pero spec_type={llama.spec_type or '(vacío)'}: "
                "el argv arranca con --spec-type none, MTP queda apagado pese al interruptor"
            )
        return out


# ── Lectura/escritura genérica de campos, usado por GET/POST /config (ver
# docs/adr/0001) — vive acá, junto al resto de config.py, porque tanto el
# daemon (dueño de la config) como cualquier UI necesitan la misma lógica de
# diff/validación antes de escribir. ──────────────────────────────────────


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


def set_in_shell(env: str) -> bool:
    """Si ``env`` viene del entorno del proceso: ahí gana sobre el ``.env``
    (``default_config``), así que reescribir el archivo no la cambia."""
    return env in os.environ


def with_secret(cfg: RinthelConfig, env: str, value: str) -> RinthelConfig:
    """``cfg`` con el secreto ``env`` (una de ``SECRET_ENVS``) reemplazado."""
    (attr,) = [a for a, name in SECRET_ENVS.items() if name == env]
    return replace(cfg, secrets=replace(cfg.secrets, **{attr: value}))


def with_local_model(cfg: RinthelConfig, model: LocalModel) -> RinthelConfig:
    """``cfg`` con ``model`` como Local model activo de ``llm``."""
    return replace(cfg, local_model=model, model_warning=None)


def default_config(instance: Instance | None = None, *, platform: Platform | None = None) -> RinthelConfig:
    """Config construida desde el ``.env`` de ``instance`` (default:
    ``Instance.discover()``), leído del archivo en cada llamada — sin
    ``load_dotenv`` al importar. Las ``RINTHEL_*`` del shell ganan.
    ``platform`` (la del proceso por defecto) elige el Validated profile. El
    Local model activo sale del catálogo y de ``instance.toml``."""
    instance = instance or Instance.discover()
    platform = platform or ("windows" if os.name == "nt" else "linux")
    file_env = {k: v for k, v in dotenv_values(instance.env_path).items() if v is not None}
    env = {**file_env, **os.environ}
    active = resolve(JsonCatalog(instance.models_catalog_path), TomlActiveModels(instance.instance_toml_path), "llm")
    return RinthelConfig(
        instance=instance,
        llama=_load(LlamaConfig, LLAMA_FIELDS, env, instance, defaults=VALIDATED_PROFILES[platform].llama),
        moe=_load(MoeConfig, MOE_FIELDS, env, instance),
        understory=_load(UnderstoryConfig, UNDERSTORY_FIELDS, env, instance),
        install=_load(InstallConfig, INSTALL_FIELDS, env, instance),
        deck=_load(DeckConfig, DECK_FIELDS, env, instance, defaults=_DECK_DEFAULTS[platform]),
        hostexecd=replace(
            _load(HostExecConfig, HOSTEXECD_FIELDS, env, instance, defaults=_HOSTEXECD_DEFAULTS[platform]),
            token=_str_env(HOSTEXECD_TOKEN_ENV, "", env).strip(),
        ),
        secrets=Secrets(**{attr: _str_env(name, "", env) for attr, name in SECRET_ENVS.items()}),
        identity=_load(IdentityConfig, IDENTITY_FIELDS, env, instance),
        legacy_env=tuple(name for name in _LEGACY_ENV if name in env),
        platform=platform,
        local_model=active.model,
        model_warning=active.warning,
    )
