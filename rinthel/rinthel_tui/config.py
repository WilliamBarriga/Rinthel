"""Single source of truth for infra paths/ports.

Replaces ``nightcity/config/rinthel-env.sh``. Unlike the bash version, there
is no need for an "export everything up front" pattern: phases receive
``cfg`` explicitly as an argument (they do not read the global environment),
so it does not matter in which order or in which process/subshell they run.

``RinthelConfig`` is composed of one sub-config per service
(``cfg.llama``, ``cfg.understory``, ``cfg.deck``, ``cfg.moe``,
``cfg.install``) — each with its own
fields, without the repeated prefix they had as loose fields of the
previous monolithic dataclass (``cfg.llama_port`` -> ``cfg.llama.port``).

Every field can be overridden with a ``RINTHEL_*`` environment variable (see
``.env.example``) — the names of those variables did NOT change with this
split, except for the special case of llama-server, which had no prefix of
its own before and is now consistent with the rest of the services
(``RINTHEL_LLAMA_PORT``/``RINTHEL_LLAMA_MODEL_PATH``/``RINTHEL_LLAMA_LOG_PATH``).

``default_config(instance)`` reads the Instance's ``.env`` (see
``instance.py``) straight from the file, without touching ``os.environ`` —
the shell's ``RINTHEL_*`` win over the file.
"""

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from rinthel_tui.instance import Instance
from rinthel_tui.lifecycle.domain.types import Platform
from rinthel_tui.models.adapters.json_catalog import JsonCatalog
from rinthel_tui.models.adapters.toml_active import TomlActiveModels
from rinthel_tui.models.domain.models import resolve
from rinthel_tui.models.domain.types import DEFAULT_REASONING_FORMAT, VOICE, Capability, LocalModel


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
    """A field loadable from an env var — it lives next to the dataclass it
    describes, so adding/removing a service field is a single line in a
    single place, instead of touching the parsing in ``default_config()``
    and separately remembering to add it to the ``validate()`` checks.

    ``port``/``positive``/``exists`` tag which ``validate()`` check applies
    to this field — see ``_ENTRIES`` below, which aggregates them
    generically instead of 3 hand-maintained lists."""

    attr: str
    env: str
    kind: type
    default: Any
    port: bool = False
    positive: bool = False
    exists: bool = False
    # Category for visual grouping in [N] CONFIGURAR — "" for
    # sub-configs with few fields that do not need it (understory/
    # deck/moe). Plain identifier (no accents) because it crosses to
    # JSON/Rust via GET /config; the displayed label is the client's
    # responsibility.
    group: str = ""


_LOADERS: dict[type, Callable[[str, Any, Mapping[str, str]], Any]] = {
    Path: _path_env,
    int: _int_env,
    float: _float_env,
    bool: _bool_env,
    str: _str_env,
}

# Parsers from a raw value (string, e.g. what arrives in a POST /config
# override) to the field's type — sibling of `_LOADERS`, which instead reads
# from an env var. Same truthiness rule as `_bool_env` for bool.
_PARSERS: dict[type, Callable[[str], Any]] = {
    Path: _p,
    int: int,
    float: float,
    bool: lambda raw: raw.strip().lower() in ("1", "on", "true", "yes"),
    str: lambda raw: raw,
}

# Type name served in GET /config (``kind``) so the client knows which
# widget to render (checkbox vs. input) without knowing Python types —
# same "no codegen" rule as ADR 0001, a small dict instead of a schema
# tool.
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
    """Instantiate ``cls`` (a config dataclass) reading each ``Field`` from
    ``source``. ``defaults`` overrides the default of some fields (a
    Platform's Validated profile). A callable ``default`` is a layout
    default: it is resolved against the ``instance`` (e.g. ``understory.dir``)."""
    defaults = defaults or {}

    def default_of(f: Field) -> Any:
        value = defaults.get(f.attr, f.default)
        return value(instance) if callable(value) else value

    return cls(**{f.attr: _LOADERS[f.kind](f.env, default_of(f), source) for f in fields})


_LOCAL_MODEL_HINT = "es del Local model: editá models.local.json y elegí el activo con «models use <id>»"

# Variables of the thecodacus/llama.cpp fork that upstream llama.cpp lacks: an
# old .env may still carry them and they are silently ignored.
_LEGACY_ENV: dict[str, str] = {
    "RINTHEL_MOE_CACHE_SLOTS": "usá RINTHEL_MOE_CACHE_MIB (--moe-cache-mib de upstream)",
    "RINTHEL_MOE_CACHE_PROFILE": "el perfil de ruteo MoE ya no existe en upstream",
    "RINTHEL_MOE_TRACE_BUILD": "llama-moe-trace ya no existe en upstream",
    "RINTHEL_MOE_TRACE_OUT_DIR": "llama-moe-trace ya no existe en upstream",
    "RINTHEL_SCHED_ASYNC_CPU": "--no-sched-async-cpu ya no existe en upstream",
    # What now belongs to each Local model (``models.local.json`` catalog and
    # ``[models]`` of ``data/instance.toml``), not to the ``.env``.
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
    # The MTP (speculative decoding) mode when the active Local model turns
    # it on (``mtp`` in its catalog entry); with ``mtp`` off the argv starts
    # with ``--spec-type none`` without looking at this value (see
    # ``lifecycle/services.py::_llama_argv``).
    spec_type: str
    spec_draft_n_max: int
    cache_type_k: str
    cache_type_v: str


# `fit_to_memory` builds the `-fit` flag (`services.py::_llama_argv`), which
# adjusts unset args to fit in device memory — it is unrelated to flash
# attention, despite what a different name might suggest.
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
    """The Local model INSTALL downloads and leaves active: the catalog's
    initial entry, with the context window measured for the Platform."""

    id: str
    name: str
    file: str
    url: str
    context_window: int
    reasoning_format: str = DEFAULT_REASONING_FORMAT


@dataclass(frozen=True)
class ValidatedProfile:
    """A Platform's Validated profile (see GLOSSARY.md), in one place:
    ``llama`` overrides the default of the hardware ``LLAMA_FIELDS`` (an
    explicit variable from the ``.env`` or the shell still wins) and
    ``model`` is the default Local model. Changing either one changes the
    ``llama-server`` argv, and that calls for a new benchmark
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
    # The LLAMA_FIELDS defaults are the Linux ones.
    "linux": ValidatedProfile(llama={}, model=_qwen(112000)),
    # Measured on the reference machine (docs/05-windows-validation.md).
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


# Upstream llama.cpp's ``--moe-cache-mib``: MiB of VRAM to cache the MoE
# experts that live on CPU. 0 = disabled (upstream default).
MOE_FIELDS: list[Field] = [
    Field("cache_mib", "RINTHEL_MOE_CACHE_MIB", int, 0),
]


@dataclass(frozen=True)
class UnderstoryConfig:
    dir: Path
    port: int
    enabled: bool


UNDERSTORY_FIELDS: list[Field] = [
    # Monorepo subtree. The real state (bundle) lives at the Instance root,
    # in data/understory; see the root docker-compose.yaml.
    Field("dir", "RINTHEL_UNDERSTORY_DIR", Path, lambda i: str(i.understory_dir)),
    Field("port", "RINTHEL_UNDERSTORY_PORT", int, 3800, port=True),
    Field("enabled", "RINTHEL_UNDERSTORY_ENABLED", bool, True),
]


@dataclass(frozen=True)
class DeckConfig:
    """What the daemon needs to know about Deck. ``host_address`` is how Deck
    reaches the host from its container: the daemon builds every URL it
    hands over with it (the llama route, voice, hostexecd); Deck never
    rewrites them."""

    host_address: str
    dir: Path
    port: int
    enabled: bool


DECK_FIELDS: list[Field] = [
    Field("host_address", "RINTHEL_DECK_HOST_ADDRESS", str, "127.0.0.1"),
    # Monorepo subtree. The real state (deck.db, pi's home) lives at the
    # Instance root, in data/deck.
    Field("dir", "RINTHEL_DECK_DIR", Path, lambda i: str(i.deck_dir)),
    Field("port", "RINTHEL_DECK_PORT", int, 4100, port=True),
    Field("enabled", "RINTHEL_DECK_ENABLED", bool, True),
]

# Default per Platform: on Linux the container shares the host network;
# Docker Desktop (Windows) reaches the host by its reserved name.
_DECK_DEFAULTS: dict[Platform, dict[str, Any]] = {
    "linux": {},
    "windows": {"host_address": "host.docker.internal"},
}


@dataclass(frozen=True)
class WhisperConfig:
    """``whisper-server`` of whisper.cpp (CPU), the managed service of
    ``stt``. The model is the active Local model, not a field."""

    bin: Path
    port: int
    log: Path
    threads: int

    @property
    def repo(self) -> Path:
        # ``<repo>/build/bin/whisper-server``: the checkout INSTALL clones.
        return self.bin.parents[2]


# Not ``exists``: voice is opt-in, a missing binary is not worth a warning
# on every Instance that never ran INSTALL with voice.
WHISPER_FIELDS: list[Field] = [
    Field("bin", "RINTHEL_WHISPER_BIN", Path, "~/whisper.cpp/build/bin/whisper-server", group="general"),
    Field("port", "RINTHEL_WHISPER_PORT", int, 8178, port=True, group="general"),
    Field("log", "RINTHEL_WHISPER_LOG_PATH", Path, lambda i: str(i.logs_dir / "whisper-server.log"), group="general"),
    Field("threads", "RINTHEL_WHISPER_THREADS", int, 4, positive=True, group="compute"),
]


@dataclass(frozen=True)
class AudioCppConfig:
    """``audiocpp_server`` of audio.cpp (CUDA), the managed service of
    ``tts``. The model and its voice are the active Local model's."""

    bin: Path
    port: int
    log: Path
    threads: int

    @property
    def repo(self) -> Path:
        # ``<repo>/build/rinthel/bin/audiocpp_server``: the checkout INSTALL clones.
        return self.bin.parents[3]


AUDIOCPP_FIELDS: list[Field] = [
    Field("bin", "RINTHEL_AUDIOCPP_BIN", Path, "~/audio.cpp/build/rinthel/bin/audiocpp_server", group="general"),
    Field("port", "RINTHEL_AUDIOCPP_PORT", int, 7860, port=True, group="general"),
    Field("log", "RINTHEL_AUDIOCPP_LOG_PATH", Path, lambda i: str(i.logs_dir / "audiocpp-server.log"), group="general"),
    Field("threads", "RINTHEL_AUDIOCPP_THREADS", int, 4, positive=True, group="compute"),
]

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
    """The Instance secrets the daemon reads. They are kept apart from
    ``_ENTRIES``: ``GET /config`` never shows them. ``service`` is the one
    the ``service`` policy requires (the TUI); ``panel`` signs the Panel
    tokens. No real default: an empty secret lets nobody through. INSTALL
    (``phase_install_instance_secrets``) and boot (``service``) generate them."""

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
    # Where INSTALL downloads the default Local model's GGUF (outside the repo).
    Field("models_dir", "RINTHEL_MODELS_DIR", Path, "~/llama.cpp/models"),
]


# A single place pairing each sub-config with its field table —
# ``RinthelConfig.validate()`` derives the 3 checks (ports, positives,
# paths) from here instead of keeping 3 separate hand-maintained lists.
# Adding a new service is one line here, not 3 in 3 different places.
# ``attr`` doubles as the prefix of error/warning messages (e.g.
# "llama.port=...") because it matches the sub-config name in
# RinthelConfig 1:1 — there is no case today where they differ.
_ENTRIES: list[tuple[str, list[Field]]] = [
    ("llama", LLAMA_FIELDS),
    ("moe", MOE_FIELDS),
    ("understory", UNDERSTORY_FIELDS),
    ("deck", DECK_FIELDS),
    ("hostexecd", HOSTEXECD_FIELDS),
    ("install", INSTALL_FIELDS),
    ("whisper", WHISPER_FIELDS),
    ("audiocpp", AUDIOCPP_FIELDS),
]


class ConfigError(Exception):
    """Config so invalid that no phase can work — raised before starting
    anything (see ``RinthelConfig.validate``)."""


@dataclass(frozen=True)
class RinthelConfig:
    instance: Instance
    llama: LlamaConfig
    moe: MoeConfig
    understory: UnderstoryConfig
    deck: DeckConfig
    install: InstallConfig
    whisper: WhisperConfig
    audiocpp: AudioCppConfig
    hostexecd: HostExecConfig = HostExecConfig(8766, True)
    secrets: Secrets = Secrets("", "")
    identity: IdentityConfig = IdentityConfig()
    # The legacy variables present when the cfg was built (shell or ``.env``).
    legacy_env: tuple[str, ...] = ()
    platform: Platform = "linux"
    # The active ``llm`` Local model that llama-server serves (or will serve
    # on the next boot). ``None``: there is no usable one and llama does not
    # start; ``model_warning`` says why.
    local_model: LocalModel | None = None
    model_warning: str | None = None
    # The active Local models of voice (Linux only), as their managed
    # services run them; ``None`` is the Capability off. ``voice_warnings``
    # says why an active key could not be used.
    stt_model: LocalModel | None = None
    tts_model: LocalModel | None = None
    voice_warnings: tuple[str, ...] = ()

    @property
    def profile(self) -> ValidatedProfile:
        return VALIDATED_PROFILES[self.platform]

    def model_of(self, capability: Capability) -> LocalModel | None:
        """The Local model the Instance serves (or will serve on the next
        boot) for ``capability``."""
        return {"llm": self.local_model, "stt": self.stt_model, "tts": self.tts_model}[capability]

    def model_llama(self) -> LlamaConfig:
        """``llama`` with the active Local model's own overrides (only the
        allow-listed ones: sampling and speculative decoding)."""
        if self.local_model is None or not self.local_model.overrides:
            return self.llama
        kinds = {f.attr: f.kind for f in LLAMA_FIELDS}
        return replace(
            self.llama,
            **{attr: _PARSERS[kinds[attr]](str(v)) for attr, v in self.local_model.overrides.items()},
        )

    def validate(self) -> list[str]:
        """Return warnings for paths that do not exist yet (non-blocking: the
        user may want to use only MONITOR/LOGS without booting anything, and
        the real failure only happens, with a clear message, in phase_spawn).
        Raise ConfigError on anything guaranteed to break any phase that runs
        (duplicate/invalid ports, numbers ≤0) — the split into sub-configs
        made it easy, for example, for two services to end up pointing at
        the same port without anyone noticing until one of them silently
        fails to "come up"."""
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
        warnings.extend(self.voice_warnings)
        warnings.extend(self._mtp_warnings())
        return warnings

    def _mtp_warnings(self) -> list[str]:
        """Warnings for the MTP combos that the ``test-tarkAIrk``
        investigation measured as unsafe (VRAM) or that ``llama.cpp`` outright
        ignores/breaks. They are not errors: one may want to save the config
        anyway (e.g. turning MTP on with batch 2048 knowing it must be lowered
        if it blows up), so they go out as warnings — they reach the client as
        the ``warnings`` of ``POST /config``, which is where the TUI paints
        them in the ``[N] CONFIGURAR`` status bar.

        Sources: ``test-tarkAIrk/logs/08`` (MTP OOM, ~650 MiB of extra compute
        buffer), ``logs/27`` (MTP + batch 2048 = 48 MiB free, reproduces the
        OOM) and ``handoff/03`` (MTP does not support ``--parallel`` > 1 nor
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


# ── Generic field read/write, used by GET/POST /config (see
# docs/adr/0001) — it lives here, with the rest of config.py, because both
# the daemon (owner of the config) and any UI need the same
# diff/validation logic before writing. ──────────────────────────────────


def stringify(value: object) -> str:
    """Same text representation that would end up in the .env — bool goes
    as "true"/"false" (what ``_bool_env``/``_PARSERS[bool]`` accept),
    not "True"/"False"."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def diff_overrides(cfg: RinthelConfig, edits: dict[str, str]) -> dict[str, str]:
    """Of everything touched (``edits``: env var -> new value as string),
    return only what actually differs from the current value in ``cfg`` —
    the minimum that must be written to the .env."""
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
    """Apply ``overrides`` (env var -> string, same shape as
    ``diff_overrides``/``update_env_file``) on a copy of ``cfg`` without
    touching the .env — used by ``POST /config`` to validate the resulting
    state (``RinthelConfig.validate()``) before actually writing."""
    kwargs: dict[str, Any] = {}
    for attr, fields in _ENTRIES:
        sub = getattr(cfg, attr)
        changes = {f.attr: _PARSERS[f.kind](overrides[f.env]) for f in fields if f.env in overrides}
        kwargs[attr] = replace(sub, **changes) if changes else sub
    return replace(cfg, **kwargs)


def set_in_shell(env: str) -> bool:
    """Whether ``env`` comes from the process environment: there it wins
    over the ``.env`` (``default_config``), so rewriting the file does not
    change it."""
    return env in os.environ


def with_secret(cfg: RinthelConfig, env: str, value: str) -> RinthelConfig:
    """``cfg`` with the secret ``env`` (one of ``SECRET_ENVS``) replaced."""
    (attr,) = [a for a, name in SECRET_ENVS.items() if name == env]
    return replace(cfg, secrets=replace(cfg.secrets, **{attr: value}))


_MODEL_ATTR: dict[Capability, str] = {"llm": "local_model", "stt": "stt_model", "tts": "tts_model"}


def with_local_model(cfg: RinthelConfig, model: LocalModel) -> RinthelConfig:
    """``cfg`` with ``model`` as the active Local model of its Capability."""
    if model.capability == "llm":
        return replace(cfg, local_model=model, model_warning=None)
    return replace(cfg, **{_MODEL_ATTR[model.capability]: model})


def without_model(cfg: RinthelConfig, capability: Capability) -> RinthelConfig:
    """``cfg`` with ``capability`` off: no active model, its service does not start."""
    return replace(cfg, **{_MODEL_ATTR[capability]: None})


def with_voice_from_instance(cfg: RinthelConfig) -> RinthelConfig:
    """``cfg`` with the active voice models re-read from the catalog and
    ``instance.toml`` (after INSTALL with voice wrote them). Voice is Linux
    only: on Windows it stays off whatever the files say. A missing key is
    the Capability off, without a warning: voice is opt-in."""
    if cfg.platform != "linux":
        return replace(cfg, stt_model=None, tts_model=None, voice_warnings=())
    catalog = JsonCatalog(cfg.instance.models_catalog_path)
    active_ids = TomlActiveModels(cfg.instance.instance_toml_path)
    models: dict[str, LocalModel | None] = {}
    warnings: list[str] = []
    for capability in VOICE:
        active = resolve(catalog, active_ids, capability) if active_ids.get(capability) else None
        models[_MODEL_ATTR[capability]] = active.model if active else None
        if active is not None and active.warning:
            warnings.append(active.warning)
    return replace(cfg, **models, voice_warnings=tuple(warnings))


def default_config(instance: Instance, *, platform: Platform) -> RinthelConfig:
    """Config built from the ``.env`` of ``instance``, read from the file on
    every call (no ``load_dotenv`` at import time). The shell's ``RINTHEL_*``
    win. ``platform`` picks the Validated profile; the caller takes it from
    ``HostInfo.platform()`` (ports-and-adapters ADR: only the composition
    looks at the OS). The active Local model comes from the catalog and
    ``instance.toml``."""
    env = {**instance.env_file(), **os.environ}
    active = resolve(JsonCatalog(instance.models_catalog_path), TomlActiveModels(instance.instance_toml_path), "llm")
    return with_voice_from_instance(RinthelConfig(
        instance=instance,
        llama=_load(LlamaConfig, LLAMA_FIELDS, env, instance, defaults=VALIDATED_PROFILES[platform].llama),
        moe=_load(MoeConfig, MOE_FIELDS, env, instance),
        understory=_load(UnderstoryConfig, UNDERSTORY_FIELDS, env, instance),
        install=_load(InstallConfig, INSTALL_FIELDS, env, instance),
        deck=_load(DeckConfig, DECK_FIELDS, env, instance, defaults=_DECK_DEFAULTS[platform]),
        whisper=_load(WhisperConfig, WHISPER_FIELDS, env, instance),
        audiocpp=_load(AudioCppConfig, AUDIOCPP_FIELDS, env, instance),
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
    ))
