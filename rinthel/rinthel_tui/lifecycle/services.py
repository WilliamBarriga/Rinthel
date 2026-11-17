"""Instancias concretas de ``LocalProcessService``/``DockerComposeService``
— un lugar único para agregar un servicio nuevo (llama-server local, o
Understory y el portal vía docker compose) sin tocar ``managed_service.py``.
"""

import sys

from rinthel_tui.config import RinthelConfig
from rinthel_tui.lifecycle.managed_service import DockerComposeService, LocalProcessService

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
LOCAL_SERVICES: list[LocalProcessService] = [LLAMA_SERVICE, HOSTEXECD_SERVICE]
DOCKER_SERVICES: list[DockerComposeService] = [UNDERSTORY_SERVICE, DECK_SERVICE]
