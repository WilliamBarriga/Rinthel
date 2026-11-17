"""``GET /theme`` (la paleta del cliente) y ``GET``/``POST /config``: el daemon es dueño de todo ``RinthelConfig``; el
cliente Rust no duplica ``config._ENTRIES`` ni parsea ``.env``. El shape
genérico de la respuesta y el ciclo validar-antes-de-escribir viven en
``config_edits.py`` — acá solo el wiring HTTP."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from rinthel_tui import config_edits
from rinthel_tui.api.access import service, service_or_admin
from rinthel_tui.api.config.dtos import ConfigPayload, ConfigUpdate, ConfigUpdateResult, ThemeResponse
from rinthel_tui.api.deps import state
from rinthel_tui.config import RinthelConfig
from rinthel_tui.theme import palette

_cfg = state("cfg")

router = APIRouter()


@router.get("/theme", response_model=ThemeResponse, dependencies=[Depends(service_or_admin)])
def get_theme():
    return {
        "canonical": {
            "fg": palette.FG,
            "accent": palette.ACCENT,
            "electric": palette.ELECTRIC,
            "warn": palette.WARN,
            "success": palette.SUCCESS,
            "hot": palette.HOT,
            "caution": palette.CAUTION,
            "glow": palette.GLOW,
            "dim": palette.DIM,
            "bg": palette.BG,
        },
        "extended": {
            "cool": palette.COOL,
            "cool_dim": palette.COOL_DIM,
            "hot_dim": palette.HOT_DIM,
            "electric_dim": palette.ELECTRIC_DIM,
            "steel": palette.STEEL,
            "steel_dim": palette.STEEL_DIM,
            "accent_dim": palette.ACCENT_DIM,
        },
        "frame_chars": list(palette.FRAME_CHARS),
    }


@router.get("/config", response_model=ConfigPayload, dependencies=[Depends(service)])
def get_config(cfg: RinthelConfig = Depends(_cfg)):
    return config_edits.config_payload(cfg)


# `exclude_none`: el cliente Rust tolera `errors`/`warnings` ausentes
# (`#[serde(default)]`) pero no `null` — un rechazo trae solo `errors`.
@router.post(
    "/config", response_model=ConfigUpdateResult, response_model_exclude_none=True, dependencies=[Depends(service)]
)
def post_config(request: Request, payload: ConfigUpdate, cfg: RinthelConfig = Depends(_cfg)):
    # Reemplaza `app.state.cfg` (no solo el archivo) por el RinthelConfig ya
    # validado tras un write propio, para que la siguiente request no siga
    # viendo el valor viejo.
    updated, result = config_edits.apply_config_overrides(cfg, payload.overrides)
    if updated is not None:
        request.app.state.cfg = updated
    return result
