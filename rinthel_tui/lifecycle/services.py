"""Instancias concretas de ``LocalProcessService``/``DockerComposeService``
— un lugar único para agregar un servicio nuevo (llama-server local, o
Understory/Pithagoras vía docker compose) sin tocar ``managed_service.py``
ni triplicar fases en ``phases.py`` como antes de este refactor.
"""

from rinthel_tui.config import RinthelConfig
from rinthel_tui.lifecycle.managed_service import DockerComposeService, LocalProcessService


# ── argv builders — idénticos a los que armaba cada phase_spawn_* antes
# de este refactor, solo movidos acá ─────────────────────────────────────


def _llama_argv(cfg: RinthelConfig) -> list[str]:
    argv = [
        str(cfg.llama.bin), "-m", str(cfg.llama.model),
        "-ngl", cfg.llama.ngl,
        "-c", str(cfg.llama.context_window),
        "-fa", "on" if cfg.llama.flash_attention else "off",
        "-fit", "on" if cfg.llama.flash_inference else "off",
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
        "--spec-type", cfg.llama.spec_type,
        "--spec-draft-n-max", str(cfg.llama.spec_draft_n_max),
    ]
    if cfg.moe.cache_slots > 0:
        argv += [
            "--moe-cache-profile", str(cfg.moe.cache_profile),
            "--moe-cache-slots", str(cfg.moe.cache_slots),
        ]
    if not cfg.llama.sched_async_cpu:
        argv += ["--no-sched-async-cpu"]
    return argv


# ── LocalProcessService ───────────────────────────────────────────────
#
# menu_label/wait_label/kill_label alimentan directamente los labels de
# PhaseSpec en specs.py — agregar un servicio nuevo acá (más su entrada en
# LOCAL_SERVICES/DOCKER_SERVICES más abajo) alcanza para que aparezca en
# BOOT/DOWN/RELOAD sin tocar specs.py.

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

UNDERSTORY_SERVICE = DockerComposeService(
    display_name="Understory",
    menu_label="UNDERSTORY  --  MCP MEMORY LAYER",
    wait_label="UNDERSTORY",
    kill_label="UNDERSTORY  --  MCP MEMORY LAYER",
    dir_of=lambda cfg: cfg.understory.dir,
    port_of=lambda cfg: cfg.understory.port,
    enabled_of=lambda cfg: cfg.understory.enabled,
    compose_service_name="understory",
    ready_url_of=lambda cfg: f"http://127.0.0.1:{cfg.understory.port}/",
)

PITHAGORAS_SERVICE = DockerComposeService(
    display_name="Pithagoras",
    menu_label="PITHAGORAS  --  PI TASK PORTAL",
    wait_label="PITHAGORAS",
    kill_label="PITHAGORAS  --  PI TASK PORTAL",
    dir_of=lambda cfg: cfg.pithagoras.dir,
    port_of=lambda cfg: cfg.pithagoras.port,
    enabled_of=lambda cfg: cfg.pithagoras.enabled,
    compose_service_name="portal",
    extra_env_of=lambda cfg: {"PORT": str(cfg.pithagoras.port)},
    build_args=("build", "--no-cache", "portal"),
    ready_url_of=lambda cfg: f"http://127.0.0.1:{cfg.pithagoras.port}/",
)


# Orden de aparición en BOOT/DOWN/RELOAD — agregar o sacar un servicio de
# estas listas alcanza para que las 4 secuencias lo reflejen (specs.py no
# tiene ninguna referencia hardcodeada a un servicio puntual).
LOCAL_SERVICES: list[LocalProcessService] = [LLAMA_SERVICE]
DOCKER_SERVICES: list[DockerComposeService] = [UNDERSTORY_SERVICE, PITHAGORAS_SERVICE]
