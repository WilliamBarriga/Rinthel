"""Prepare a fresh Linux monorepo without host-specific Docker networking."""
import json
import os
import secrets
from pathlib import Path

from dotenv import dotenv_values

from rinthel_tui.env_file import update_env_file

COMPOSE_FILE = "docker-compose.ubuntu.yml"
HOST_EXEC_COMPOSE_FILE = COMPOSE_FILE + ":compose/ubuntu-host-exec.override.yaml"


def is_selected(value: str | None) -> bool:
    return value in {COMPOSE_FILE, HOST_EXEC_COMPOSE_FILE}


def prepare(root: Path) -> None:
    if os.name != "posix":
        raise RuntimeError("Este perfil requiere Linux")
    import grp

    env_path = root / ".env"
    values = dict(dotenv_values(env_path)) if env_path.exists() else {}
    if values.get("COMPOSE_FILE") not in (None, "") and not is_selected(values["COMPOSE_FILE"]):
        raise RuntimeError("Ya existe otro COMPOSE_FILE; revisa .env antes de seleccionar el perfil Ubuntu")
    host_exec = (root / "compose/ubuntu-host-exec.override.yaml").is_file()
    if host_exec and not (root / "extensions/rinthel-host-exec/index.ts").is_file():
        raise RuntimeError("El overlay host exec existe pero su extensión está ausente")
    if values.get("COMPOSE_FILE") == HOST_EXEC_COMPOSE_FILE and not host_exec:
        raise RuntimeError("La configuración necesita el overlay host exec que falta en este checkout")
    selected_compose = HOST_EXEC_COMPOSE_FILE if host_exec else COMPOSE_FILE
    if host_exec:
        from rinthel_tui.install.host_exec import prepare_host_exec
        prepare_host_exec(root, root / "pithagoras")
    data = root / "data"
    model = data / "models" / "Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf"
    defaults = {
        "COMPOSE_FILE": selected_compose,
        "RINTHEL_LLAMACPP_REPO_DIR": str(data / "llama.cpp"),
        "RINTHEL_LLAMA_BIN": str(data / "llama.cpp/build-cuda/bin/llama-server"),
        "RINTHEL_LLAMA_MODEL_PATH": str(model),
        "RINTHEL_LLAMA_LOG_PATH": str(root / "logs/llama-server.log"),
        "RINTHEL_CONTEXT_WINDOW": "65536", "RINTHEL_N_CPU_MOE": "34",
        "RINTHEL_UBATCH_SIZE": "2048", "RINTHEL_BATCH_SIZE": "2048",
        "RINTHEL_SPEC_TYPE": "none", "RINTHEL_SCHED_ASYNC_CPU": "false",
        "RINTHEL_CACHE_TYPE_K": "q8_0", "RINTHEL_CACHE_TYPE_V": "q8_0",
        "RINTHEL_MOE_CACHE_SLOTS": "0",
        "PUID": str(os.getuid()), "PGID": str(os.getgid()),
        "WORKSPACES_DIR": str(data / "workspaces"),
        "PORTAL_PASSWORD": secrets.token_urlsafe(18),
        "PORTAL_SECRET": secrets.token_hex(32),
    }
    token = values.get("UNDERSTORY_TOKEN") or values.get("AUTH_TOKEN") or secrets.token_hex(24)
    defaults.update(UNDERSTORY_TOKEN=token, AUTH_TOKEN=token)
    if values.get("AUTH_TOKEN") and values.get("UNDERSTORY_TOKEN") and values["AUTH_TOKEN"] != values["UNDERSTORY_TOKEN"]:
        raise ValueError("AUTH_TOKEN y UNDERSTORY_TOKEN deben coincidir; no se reemplazaron secretos")
    try:
        defaults["DOCKER_GID"] = str(grp.getgrnam("docker").gr_gid)
    except KeyError:
        pass  # Rerun after Docker installation to discover the actual group.
    missing = {key: value for key, value in defaults.items() if not values.get(key)}
    if host_exec and values.get("COMPOSE_FILE") == COMPOSE_FILE:
        missing["COMPOSE_FILE"] = selected_compose
    # Quote literals so spaces, # and $ in paths survive dotenv and Compose.
    update_env_file(env_path, {k: "'" + v.replace("'", "\\'") + "'" for k, v in missing.items()})
    values.update(missing)
    agent = data / "pithagoras/home/.pi/agent"
    for directory in (agent, data / "pithagoras/bin", data / "pithagoras/sessions",
                      data / "pithagoras/channels", data / "pithagoras/agent-home",
                      Path(values["WORKSPACES_DIR"]).expanduser(), data / "models"):
        directory.mkdir(parents=True, exist_ok=True)
    models_path = agent / "models.json"
    models = json.loads(models_path.read_text()) if models_path.exists() else {"providers": {}}
    providers = models.setdefault("providers", {})
    providers["local-llm"] = {
        "baseUrl": f"http://127.0.0.1:{values.get('RINTHEL_LLAMA_PORT') or '8080'}/v1",
        "api": "openai-completions", "apiKey": "local",
        "compat": {"supportsDeveloperRole": False, "supportsReasoningEffort": False},
        "models": [{"id": values["RINTHEL_LLAMA_MODEL_PATH"], "name": "Qwen3.6 35B Local"}],
    }
    models_path.write_text(json.dumps(models, indent=2) + "\n")
    bundle = data / "understory"
    for name in ("agents", "extensions", "projects", "reference", "users"):
        (bundle / name).mkdir(parents=True, exist_ok=True)
    for name in ("index.md", "log.md", *(f"{n}/index.md" for n in ("agents", "extensions", "projects", "reference", "users"))):
        target = bundle / name
        if not target.exists():
            target.write_text(f"# {target.parent.name if target.name == 'index.md' else 'log'}\n")
    print("[install] Perfil Ubuntu preparado; secretos conservados en .env")


if __name__ == "__main__":
    from rinthel_tui.config import REPO_ROOT
    prepare(REPO_ROOT)
