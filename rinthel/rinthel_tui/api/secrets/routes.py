"""``POST /secrets/rotate``: rota ``RINTHEL_SERVICE_SECRET`` o
``RINTHEL_PANEL_SECRET`` con el daemon corriendo. Lo síncrono —
``Instance.rotate_secret`` y el ``cfg`` nuevo — vive en
``config_edits.rotate_secret``; acá se reemplaza el ``cfg`` vivo, igual
que ``POST /config``. Ningún servicio que el daemon gestiona hoy lee estos
secretos, así que no hay nada que recrear y ``results`` queda vacío. Policy
``service``: solo la TUI rota."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from rinthel_tui import config_edits
from rinthel_tui.api.access import service
from rinthel_tui.api.deps import state
from rinthel_tui.api.secrets.dtos import SecretRotateRequest, SecretRotateResult
from rinthel_tui.config import RinthelConfig
from rinthel_tui.instance import RotatableSecret

_cfg = state("cfg")

router = APIRouter()


@router.post(
    "/secrets/rotate",
    response_model=SecretRotateResult,
    response_model_exclude_none=True,
    dependencies=[Depends(service)],
)
def rotate_secret(
    request: Request,
    payload: SecretRotateRequest,
    cfg: RinthelConfig = Depends(_cfg),
):
    try:
        updated, new_secret = config_edits.rotate_secret(cfg, payload.key)
    except config_edits.SecretInShell as exc:
        raise HTTPException(409, str(exc)) from exc
    request.app.state.cfg = updated
    service_secret = new_secret if payload.key == RotatableSecret.SERVICE else None
    return {"results": [], "service_secret": service_secret}
