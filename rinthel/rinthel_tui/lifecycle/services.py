"""Instancias concretas de ``LocalProcessService``/``DockerComposeService``
— un lugar único para agregar un servicio nuevo (llama-server local, o
Understory y el portal vía docker compose) sin tocar ``managed_service.py``.
"""

import json
import sys
from pathlib import Path

from rinthel_tui.config import RinthelConfig
from rinthel_tui.lifecycle.managed_service import DockerComposeService, LocalProcessService
from rinthel_tui.models.domain.types import Capability

# ── argv builders ─────────────────────────────────────────────────────────


def _llama_argv(cfg: RinthelConfig) -> list[str]:
    """El argv del Validated profile con el Local model activo: cualquier
    cambio de orden o de flags pide un benchmark nuevo
    (``docs/05-windows-validation.md``). Sin Local model activo no hay nada
    que lanzar (``specs.boot_plan`` deja a llama-server fuera); parar por
    puerto no necesita el argv."""
    model = cfg.local_model
    if model is None:
        return []
    llama = cfg.model_llama()
    argv = [
        str(llama.bin), "-m", str(model.gguf),
        "-ngl", llama.ngl,
        "-c", str(model.context_window),
        "-fa", "on" if llama.flash_attention else "off",
        "-fit", "on" if llama.fit_to_memory else "off",
        # 0.0.0.0, no 127.0.0.1 (el default de llama-server): Understory
        # corre en un container Docker y llega acá vía host.docker.internal
        # (host-gateway), que no alcanza un bind en loopback puro.
        "--host", "0.0.0.0",
        "--port", str(llama.port),
        "--n-cpu-moe", str(llama.n_cpu_moe),
        "--threads-batch", str(llama.threads_batch),
        "--threads", str(llama.threads),
        "--ubatch-size", str(llama.ubatch_size),
        "--batch-size", str(llama.batch_size),
        "--parallel", str(llama.parallel),
        "--temp", str(llama.temperature),
        "--top-p", str(llama.top_p),
        "--top-k", str(llama.top_k),
        "--min-p", str(llama.min_p),
        "--repeat-penalty", str(llama.repeat_penalty),
        "--cache-reuse", str(llama.cache_reuse),
        "--cache-ram", str(llama.cache_ram),
        "--load-mode", llama.load_mode,
        # MTP lo prende el Local model (``mtp``): apagado, el modo se fuerza a
        # "none" sin mirar spec_type; prendido, manda spec_type.
        "--spec-type", llama.spec_type if model.mtp else "none",
        "--spec-draft-n-max", str(llama.spec_draft_n_max),
        "--cache-type-k", llama.cache_type_k,
        "--cache-type-v", llama.cache_type_v,
    ]
    # --mmproj se omite con MTP: llama.cpp no lo soporta junto a spec
    # decoding. La entrada del catálogo no cambia; solo se saltea el flag.
    if model.mmproj is not None and not model.mtp:
        argv += ["--mmproj", str(model.mmproj)]
    if cfg.moe.cache_mib > 0:
        argv += ["--moe-cache-mib", str(cfg.moe.cache_mib)]
    # Not tuning: where Deck saves and restores each Session's slot. It
    # changes no inference value, so it goes after the Validated profile.
    argv += ["--slot-save-path", str(_slots_dir(cfg))]
    return argv


def _slots_dir(cfg: RinthelConfig):
    """Deck's own directory of saved slots (``data/deck/llama-slots``):
    Deck lists and deletes them to keep them under its byte budget."""
    return cfg.instance.deck_data_dir / "llama-slots"


def _whisper_argv(cfg: RinthelConfig) -> list[str]:
    """``whisper-server`` of whisper.cpp with the active ``stt`` model, on
    loopback: Deck reaches it through the host network (Linux only). Flags:
    https://github.com/ggml-org/whisper.cpp/blob/a2b36eb677918d4f9ab1db7b8a7ff968563ed163/examples/server/server.cpp"""
    model = cfg.stt_model
    if model is None:
        return []
    return [
        str(cfg.whisper.bin),
        "--host", "127.0.0.1",
        "--port", str(cfg.whisper.port),
        "--model", str(model.gguf),
        "--language", "auto",
        "--threads", str(cfg.whisper.threads),
    ]


def _audiocpp_server_config(cfg: RinthelConfig) -> Path:
    return cfg.instance.data_dir / "audiocpp-server.json"


def _audiocpp_argv(cfg: RinthelConfig) -> list[str]:
    return [str(cfg.audiocpp.bin), "--config", str(_audiocpp_server_config(cfg))]


def _audiocpp_files(cfg: RinthelConfig) -> dict[Path, str]:
    """The ``ServerConfig`` of audio.cpp (``app/server/config.{h,cpp}`` at
    5ba81ac), rewritten on every spawn. One model, loaded at start (``/health``
    answers once it is in memory), so no ``lazy_load`` nor ``idle_unload_ms``.
    No UI: its ``/v1/ui/*`` routes install and delete models. The ``id`` is
    the catalog's, the ``model`` of a request. INSTALL builds only Pocket-TTS
    (``--models pocket_tts``), so that is the family. The fixed voice of the
    entry, if any, is the default preset."""
    model = cfg.tts_model
    if model is None:
        return {}
    entry: dict[str, object] = {
        "id": model.id,
        "family": "pocket_tts",
        "path": str(model.gguf),
        "task": "tts",
        "mode": "streaming",
    }
    if model.voice is not None:
        entry["default_voice_preset"] = {"voice_ref": str(model.voice)}
    server = {
        "host": "127.0.0.1",
        "port": cfg.audiocpp.port,
        "backend": "cuda",
        "device": 0,
        "threads": cfg.audiocpp.threads,
        "ui": False,
        "lazy_load": False,
        "idle_unload_ms": 0,
        "max_loaded_models": 1,
        "models": [entry],
    }
    return {_audiocpp_server_config(cfg): json.dumps(server, indent=2) + "\n"}


# ── LocalProcessService ───────────────────────────────────────────────
#
# menu_label/wait_label/kill_label alimentan directamente los labels de
# PhaseSpec en specs.py — agregar un servicio nuevo acá (más su entrada en
# LOCAL_SERVICES/DOCKER_SERVICES más abajo) alcanza para que aparezca en
# BOOT/TERMINATE/RELOAD sin tocar specs.py.

LLAMA_SERVICE = LocalProcessService(
    display_name="llama-server",
    menu_label="LLAMA-SERVER",
    wait_label="LLAMA-SERVER",
    kill_label="LLAMA-SERVER  --  LOCAL MODEL",
    build_argv=_llama_argv,
    port_of=lambda cfg: cfg.llama.port,
    log_of=lambda cfg: cfg.llama.log,
    dirs_of=lambda cfg: [_slots_dir(cfg)],
    enabled_of=lambda cfg: cfg.llama.enabled,
    ready_url_of=lambda cfg: f"http://127.0.0.1:{cfg.llama.port}/v1/models",
    default_ready_timeout=90,
    ready_poll_interval=2.0,
    on_timeout_hint="Levanta el modelo local antes de usar understory.",
)

# Voice (Linux only): each one runs while its Capability has an active
# Local model (``[models] stt``/``tts`` in ``instance.toml``).
WHISPER_SERVICE = LocalProcessService(
    display_name="whisper-server",
    menu_label="WHISPER-SERVER  --  STT",
    wait_label="WHISPER-SERVER",
    kill_label="WHISPER-SERVER  --  STT",
    build_argv=_whisper_argv,
    port_of=lambda cfg: cfg.whisper.port,
    log_of=lambda cfg: cfg.whisper.log,
    enabled_of=lambda cfg: cfg.platform == "linux" and cfg.stt_model is not None,
    ready_url_of=lambda cfg: f"http://127.0.0.1:{cfg.whisper.port}/health",
    default_ready_timeout=60,
    ready_poll_interval=1.0,
)

AUDIOCPP_SERVICE = LocalProcessService(
    display_name="audiocpp-server",
    menu_label="AUDIOCPP-SERVER  --  TTS",
    wait_label="AUDIOCPP-SERVER",
    kill_label="AUDIOCPP-SERVER  --  TTS",
    build_argv=_audiocpp_argv,
    files_of=_audiocpp_files,
    port_of=lambda cfg: cfg.audiocpp.port,
    log_of=lambda cfg: cfg.audiocpp.log,
    enabled_of=lambda cfg: cfg.platform == "linux" and cfg.tts_model is not None,
    ready_url_of=lambda cfg: f"http://127.0.0.1:{cfg.audiocpp.port}/health",
    default_ready_timeout=60,
    ready_poll_interval=1.0,
)

# The managed service of each Capability.
MODEL_SERVICES: dict[Capability, LocalProcessService] = {
    "llm": LLAMA_SERVICE,
    "stt": WHISPER_SERVICE,
    "tts": AUDIOCPP_SERVICE,
}

# hostexecd: runs an admin's commands on the host for Deck (Linux only). It
# reads its port, token and Instance root from the environment the daemon
# hands it, and binds the host loopback.
HOSTEXECD_SERVICE = LocalProcessService(
    display_name="hostexecd",
    menu_label="HOSTEXECD  --  HOST EXEC",
    wait_label="HOSTEXECD",
    kill_label="HOSTEXECD  --  HOST EXEC",
    build_argv=lambda cfg: [sys.executable, "-m", "hostexecd.daemon"],
    port_of=lambda cfg: cfg.hostexecd.port,
    log_of=lambda cfg: cfg.instance.logs_dir / "hostexecd.log",
    env_of=lambda cfg: {
        "RINTHEL_HOSTEXECD_PORT": str(cfg.hostexecd.port),
        "RINTHEL_HOSTEXECD_TOKEN": cfg.hostexecd.token,
        "RINTHEL_INSTANCE_ROOT": str(cfg.instance.root),
    },
    enabled_of=lambda cfg: cfg.platform == "linux" and cfg.hostexecd.enabled,
    ready_url_of=lambda cfg: f"http://127.0.0.1:{cfg.hostexecd.port}/health",
    default_ready_timeout=20,
    ready_poll_interval=0.5,
)


def _deck_host_exec_env(cfg: RinthelConfig) -> dict[str, str]:
    """How Deck reaches hostexecd: its URL, built with ``deck.host_address``,
    and the token. Both empty where hostexecd does not run (Windows, or
    disabled): set in the environment of ``docker compose``, they win over the
    root ``.env``, so Deck loads no host exec tools."""
    if not HOSTEXECD_SERVICE.enabled_of(cfg):
        return {"RINTHEL_HOSTEXECD_URL": "", "RINTHEL_HOSTEXECD_TOKEN": ""}
    return {
        "RINTHEL_HOSTEXECD_URL": f"http://{cfg.deck.host_address}:{cfg.hostexecd.port}",
        "RINTHEL_HOSTEXECD_TOKEN": cfg.hostexecd.token,
    }


# ── DockerComposeService ──────────────────────────────────────────────
#
# Comparten un único docker-compose.yaml en la raíz de la Instance
# (`extends:` de understory/, `include:` de deck/), así que todos los
# ``dir_of`` apuntan a ``cfg.instance.root`` — no a ``cfg.understory.dir``/
# ``cfg.deck.dir``, que describen dónde vive el *código fuente* del
# componente, un concepto distinto de "desde dónde corro docker compose".

UNDERSTORY_SERVICE = DockerComposeService(
    display_name="Understory",
    menu_label="UNDERSTORY  --  MCP MEMORY LAYER",
    wait_label="UNDERSTORY",
    kill_label="UNDERSTORY  --  MCP MEMORY LAYER",
    dir_of=lambda cfg: cfg.instance.root,
    port_of=lambda cfg: cfg.understory.port,
    enabled_of=lambda cfg: cfg.understory.enabled,
    compose_service_name="understory",
    ready_url_of=lambda cfg: f"http://127.0.0.1:{cfg.understory.port}/",
)

# The port Understory listens on inside its container, whatever the host
# publishes it on (``understory/docker-compose.yml``).
UNDERSTORY_CONTAINER_PORT = 3800


def understory_url(cfg: RinthelConfig) -> str | None:
    """How Deck reaches Understory for Memoria, per Platform: the published
    port on the host loopback on Linux (Deck on the host network), the
    service name on the network Deck and Understory share on Windows (Deck in
    a bridge). ``None`` when Understory is off: no Session has Memoria."""
    if not UNDERSTORY_SERVICE.enabled_of(cfg):
        return None
    if cfg.platform == "windows":
        return f"http://understory:{UNDERSTORY_CONTAINER_PORT}"
    return f"http://127.0.0.1:{cfg.understory.port}"


# Deck, el portal web de la Instance.
DECK_SERVICE = DockerComposeService(
    display_name="Deck",
    menu_label="DECK  --  WEB PORTAL",
    wait_label="DECK",
    kill_label="DECK  --  WEB PORTAL",
    dir_of=lambda cfg: cfg.instance.root,
    port_of=lambda cfg: cfg.deck.port,
    enabled_of=lambda cfg: cfg.deck.enabled,
    compose_service_name="deck",
    extra_env_of=lambda cfg: {"RINTHEL_DECK_PORT": str(cfg.deck.port), **_deck_host_exec_env(cfg)},
    build_args=("build", "deck"),
    ready_url_of=lambda cfg: f"http://127.0.0.1:{cfg.deck.port}/api/auth/status",
)

# Orden de aparición en BOOT/TERMINATE/RELOAD — agregar o sacar un servicio de
# estas listas alcanza para que los planes lo reflejen.
LOCAL_SERVICES: list[LocalProcessService] = [LLAMA_SERVICE, WHISPER_SERVICE, AUDIOCPP_SERVICE, HOSTEXECD_SERVICE]
DOCKER_SERVICES: list[DockerComposeService] = [UNDERSTORY_SERVICE, DECK_SERVICE]
