"""Lógica de ``GET``/``POST /config`` — separada del wiring HTTP para poder
testear el shape genérico de ``/config`` y el ciclo validar-antes-de-escribir
sin FastAPI ni el ``cfg`` global del daemon de por medio. ``daemon.py`` sigue
siendo el único dueño de ``cfg``: estas funciones lo reciben como parámetro
y, en el caso de ``apply_config_overrides``, devuelven el ``RinthelConfig``
nuevo para que el caller decida si reemplazarlo.
"""

from pathlib import Path

from rinthel_tui import config
from rinthel_tui.config import ConfigError, RinthelConfig
from rinthel_tui.env_file import update_env_file
from rinthel_tui.lifecycle.services import LLAMA_SERVICE, PITHAGORAS_SERVICE, UNDERSTORY_SERVICE

# display_name de cada sub-config con instancia de servicio real — moe/install
# no tienen una (no son LocalProcessService/DockerComposeService), caen al
# fallback `attr.upper()` en `config_payload`.
_DISPLAY_NAMES = {
    "llama": LLAMA_SERVICE.display_name,
    "understory": UNDERSTORY_SERVICE.display_name,
    "pithagoras": PITHAGORAS_SERVICE.display_name,
}


def config_payload(cfg: RinthelConfig) -> dict:
    """Shape genérico de ``GET /config``. Itera ``config._ENTRIES`` en vez de
    listar sub-configs a mano, así que sumar un ``Field``/sub-config nuevo en
    ``config.py`` alcanza para que aparezca acá sin tocar el daemon ni el
    cliente Rust."""
    services = []
    for attr, fields in config._ENTRIES:
        sub = getattr(cfg, attr)
        enabled_field = next((f for f in fields if f.attr == "enabled"), None)
        services.append(
            {
                "attr": attr,
                "display_name": _DISPLAY_NAMES.get(attr, attr.upper()),
                "enabled": getattr(sub, "enabled") if enabled_field else None,
                # env var del toggle — separado de "enabled" porque el
                # cliente lo necesita para armar el override al tildar/
                # destildar (mismo dict env->string que el resto de POST
                # /config), y no está en "fields" (se filtra abajo).
                "enabled_env": enabled_field.env if enabled_field else None,
                "fields": [
                    {
                        "attr": f.attr,
                        "env": f.env,
                        "kind": config.KIND_NAMES[f.kind],
                        "group": f.group,
                        "value": config.stringify(getattr(sub, f.attr)),
                    }
                    for f in fields
                    if f.attr != "enabled"  # ya sale en el "enabled" de arriba
                ],
            }
        )
    return {"services": services}


def apply_config_overrides(
    cfg: RinthelConfig, edits: dict[str, str], env_path: Path, env_example_path: Path
) -> tuple[RinthelConfig | None, dict]:
    """Valida ``edits`` (env var -> valor nuevo como string) contra ``cfg``
    antes de escribir — arma un ``RinthelConfig`` hipotético con
    ``config.with_overrides`` y corre ``.validate()``; si salta
    ``ConfigError`` (puertos duplicados/inválidos, numéricos ≤0) no toca el
    ``.env``. Devuelve ``(nuevo_cfg, payload de respuesta)`` — ``nuevo_cfg``
    es ``None`` cuando no había nada que escribir o cuando falló la
    validación; el caller (``daemon.post_config``) es quien decide
    reemplazar su ``cfg`` en memoria con él."""
    to_write = config.diff_overrides(cfg, edits)
    if not to_write:
        return None, {"ok": True, "written": 0, "warnings": []}
    try:
        updated = config.with_overrides(cfg, to_write)
        warnings = updated.validate()
    except ConfigError as e:
        return None, {"ok": False, "written": 0, "errors": str(e).split("; ")}
    update_env_file(env_path, to_write, seed_from=env_example_path)
    return updated, {"ok": True, "written": len(to_write), "warnings": warnings}
