"""Instancias concretas de ``LocalProcessService``/``DockerComposeService``
— un lugar único para agregar un servicio nuevo (llama-server local, o
Understory y el portal vía docker compose) sin tocar ``managed_service.py``.
"""

from pathlib import Path

from rinthel_tui.config import RinthelConfig
from rinthel_tui.lifecycle.managed_service import DockerComposeService, LocalProcessService

# ── argv builders ─────────────────────────────────────────────────────────


def _llama_argv(cfg: RinthelConfig) -> list[str]:
    """El argv del Validated profile: cualquier cambio de orden o de flags
    pide un benchmark nuevo (``docs/05-windows-validation.md``)."""
    argv = [
        str(cfg.llama.bin), "-m", str(cfg.llama.model),
        "-ngl", cfg.llama.ngl,
        "-c", str(cfg.llama.context_window),
        "-fa", "on" if cfg.llama.flash_attention else "off",
        "-fit", "on" if cfg.llama.fit_to_memory else "off",
        # 0.0.0.0, no 127.0.0.1 (el default de llama-server): Understory
        # corre en un container Docker y llega acá vía host.docker.internal
        # (host-gateway), que no alcanza un bind en loopback puro.
        "--host", "0.0.0.0",
        "--port", str(cfg.llama.port),
        "--n-cpu-moe", str(cfg.llama.n_cpu_moe),
        "--threads-batch", str(cfg.llama.threads_batch),
        "--threads", str(cfg.llama.threads),
        "--ubatch-size", str(cfg.llama.ubatch_size),
        "--batch-size", str(cfg.llama.batch_size),
        "--parallel", str(cfg.llama.parallel),
        "--temp", str(cfg.llama.temperature),
        "--top-p", str(cfg.llama.top_p),
        "--top-k", str(cfg.llama.top_k),
        "--min-p", str(cfg.llama.min_p),
        "--repeat-penalty", str(cfg.llama.repeat_penalty),
        "--cache-reuse", str(cfg.llama.cache_reuse),
        "--cache-ram", str(cfg.llama.cache_ram),
        "--load-mode", cfg.llama.load_mode,
        # Interruptor único de MTP: apagado, el modo se fuerza a "none" sin
        # mirar spec_type (así RINTHEL_MTP_ENABLED=false apaga MTP aunque
        # .env todavía traiga RINTHEL_SPEC_TYPE=draft-mtp); prendido, manda
        # spec_type (default draft-mtp).
        "--spec-type", cfg.llama.spec_type if cfg.llama.mtp_enabled else "none",
        "--spec-draft-n-max", str(cfg.llama.spec_draft_n_max),
        "--cache-type-k", cfg.llama.cache_type_k,
        "--cache-type-v", cfg.llama.cache_type_v,
    ]
    # --mmproj se omite con MTP: llama.cpp no lo soporta junto a spec
    # decoding. El path y su toggle quedan guardados igual — solo se saltea
    # el flag en este arranque.
    if cfg.llama.mmproj_enabled and cfg.llama.mmproj and not cfg.llama.mtp_enabled:
        # str (no Path) en LlamaConfig: expandimos "~" acá, el argv va
        # directo al proceso sin pasar por un shell.
        argv += ["--mmproj", str(Path(cfg.llama.mmproj).expanduser())]
    if cfg.moe.cache_mib > 0:
        argv += ["--moe-cache-mib", str(cfg.moe.cache_mib)]
    return argv


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
    kill_label="LLAMA-SERVER  --  Qwen3.6-35B-A3B-MTP",
    build_argv=_llama_argv,
    port_of=lambda cfg: cfg.llama.port,
    log_of=lambda cfg: cfg.llama.log,
    enabled_of=lambda cfg: cfg.llama.enabled,
    ready_url_of=lambda cfg: f"http://127.0.0.1:{cfg.llama.port}/v1/models",
    default_ready_timeout=90,
    ready_poll_interval=2.0,
    on_timeout_hint="Levanta el modelo local antes de usar understory.",
)

# ── DockerComposeService ──────────────────────────────────────────────
#
# Comparten un único docker-compose.yaml en la raíz de la Instance
# (`include:` de understory/ y del portal), así que todos los ``dir_of``
# apuntan a ``cfg.instance.root`` — no a ``cfg.understory.dir``/
# ``cfg.pithagoras.dir``, que describen dónde vive el *código fuente* del
# subtree (lo usa install.py), un concepto distinto de "desde dónde corro
# docker compose".

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

# El portal heredado, hasta que Deck lo reemplace.
PITHAGORAS_SERVICE = DockerComposeService(
    display_name="Pithagoras",
    menu_label="PITHAGORAS  --  PI TASK PORTAL",
    wait_label="PITHAGORAS",
    kill_label="PITHAGORAS  --  PI TASK PORTAL",
    dir_of=lambda cfg: cfg.instance.root,
    port_of=lambda cfg: cfg.pithagoras.port,
    enabled_of=lambda cfg: cfg.pithagoras.enabled,
    compose_service_name="portal",
    extra_env_of=lambda cfg: {"PORT": str(cfg.pithagoras.port)},
    build_args=("build", "portal"),
    ready_url_of=lambda cfg: f"http://127.0.0.1:{cfg.pithagoras.port}/",
)

# Deck, el portal web. Vive junto al heredado, en su propio puerto, hasta
# que lo reemplace.
DECK_SERVICE = DockerComposeService(
    display_name="Deck",
    menu_label="DECK  --  WEB PORTAL",
    wait_label="DECK",
    kill_label="DECK  --  WEB PORTAL",
    dir_of=lambda cfg: cfg.instance.root,
    port_of=lambda cfg: cfg.deck.port,
    enabled_of=lambda cfg: cfg.deck.enabled,
    compose_service_name="deck",
    extra_env_of=lambda cfg: {"RINTHEL_DECK_PORT": str(cfg.deck.port)},
    build_args=("build", "deck"),
    ready_url_of=lambda cfg: f"http://127.0.0.1:{cfg.deck.port}/api/auth/status",
)

# Orden de aparición en BOOT/TERMINATE/RELOAD — agregar o sacar un servicio de
# estas listas alcanza para que los planes lo reflejen.
LOCAL_SERVICES: list[LocalProcessService] = [LLAMA_SERVICE]
DOCKER_SERVICES: list[DockerComposeService] = [UNDERSTORY_SERVICE, PITHAGORAS_SERVICE, DECK_SERVICE]
