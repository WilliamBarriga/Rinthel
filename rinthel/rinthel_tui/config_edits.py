"""Lógica de ``GET``/``POST /config`` — separada del wiring HTTP para poder
testear el shape genérico de ``/config`` y el ciclo validar-antes-de-escribir
sin FastAPI de por medio. El dueño de ``cfg`` es la app (``app.state.cfg``,
ver ``api/config/routes.py``): estas funciones lo reciben como parámetro y, en el caso de ``apply_config_overrides`` y
``rotate_secret``, devuelven el ``RinthelConfig`` nuevo para que el caller decida si reemplazarlo.
"""

from rinthel_tui import config
from rinthel_tui.config import ConfigError, RinthelConfig
from rinthel_tui.env_file import update_env_file
from rinthel_tui.instance import RotatableSecret
from rinthel_tui.lifecycle.services import DECK_SERVICE, HOSTEXECD_SERVICE, LLAMA_SERVICE, UNDERSTORY_SERVICE

# display_name de cada sub-config con instancia de servicio real — moe/install
# no tienen una (no son LocalProcessService/DockerComposeService), caen al
# fallback `attr.upper()` en `config_payload`.
_DISPLAY_NAMES = {
    "llama": LLAMA_SERVICE.display_name,
    "understory": UNDERSTORY_SERVICE.display_name,
    "deck": DECK_SERVICE.display_name,
    "hostexecd": HOSTEXECD_SERVICE.display_name,
}


# The Local model's fields: speculative decoding is tuned per Local model
# (its ``overrides`` whitelist), so ``[N] CONFIGURAR`` does not offer it.
_LOCAL_MODEL_FIELDS = frozenset({("llama", "spec_type"), ("llama", "spec_draft_n_max")})

# The ``llama`` groups the Validated profile covers: hardware and cache. A
# field of these groups carries the profile's value so the client can mark an
# override that differs from it.
_PROFILE_GROUPS = frozenset({"compute", "cache"})


def _profile_value(cfg: RinthelConfig, attr: str, f: config.Field) -> str | None:
    if attr != "llama" or f.group not in _PROFILE_GROUPS:
        return None
    return config.stringify(cfg.profile.llama.get(f.attr, f.default))


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
                "enabled": sub.enabled if enabled_field else None,
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
                        "profile": _profile_value(cfg, attr, f),
                    }
                    for f in fields
                    # ``enabled`` ya sale arriba; los del Local model no se configuran acá.
                    if f.attr != "enabled" and (attr, f.attr) not in _LOCAL_MODEL_FIELDS
                ],
            }
        )
    return {"services": services}


def apply_config_overrides(cfg: RinthelConfig, edits: dict[str, str]) -> tuple[RinthelConfig | None, dict]:
    """Valida ``edits`` (env var -> valor nuevo como string) contra ``cfg``
    antes de escribir — arma un ``RinthelConfig`` hipotético con
    ``config.with_overrides`` y corre ``.validate()``; si salta
    ``ConfigError`` (puertos duplicados/inválidos, numéricos ≤0) no toca el
    ``.env`` de la Instance. Devuelve ``(nuevo_cfg, payload de respuesta)`` — ``nuevo_cfg``
    es ``None`` cuando no había nada que escribir o cuando falló la
    validación; el caller (``api/config/routes.py::post_config``) es quien decide
    reemplazar su ``cfg`` en memoria con él."""
    to_write = config.diff_overrides(cfg, edits)
    if not to_write:
        return None, {"ok": True, "written": 0, "warnings": []}
    try:
        updated = config.with_overrides(cfg, to_write)
        warnings = updated.validate()
    except ConfigError as e:
        return None, {"ok": False, "written": 0, "errors": str(e).split("; ")}
    update_env_file(cfg.instance.env_path, to_write, seed_from=cfg.instance.env_example_path)
    return updated, {"ok": True, "written": len(to_write), "warnings": warnings}


class SecretInShell(Exception):
    """El secreto a rotar viene del entorno del daemon, no del ``.env``."""


def rotate_secret(cfg: RinthelConfig, key: RotatableSecret) -> tuple[RinthelConfig, str]:
    """Rota ``key`` en el ``.env`` de la Instance y devuelve ``(cfg con el
    secreto nuevo, secreto nuevo)``. Levanta ``SecretInShell`` antes de
    escribir nada si ``key`` viene del shell: la rotación sería un no-op
    silencioso."""
    if config.set_in_shell(key):
        raise SecretInShell(f"{key} viene del entorno del daemon, no del .env — sacala del shell y reiniciá")
    cfg.instance.rotate_secret(key)
    new_secret = cfg.instance.get(key) or ""
    return config.with_secret(cfg, key, new_secret), new_secret
