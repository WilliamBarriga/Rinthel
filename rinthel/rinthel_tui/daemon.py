"""Punto de entrada del daemon FastAPI de Rinthel — infraestructura
persistente e independiente del cliente: el daemon Python es lo que
sobrevive entre sesiones de la TUI, el binario Rust es el cliente
reemplazable. La app en sí se arma en ``rinthel_tui/api/`` (``create_app``,
un router por área).

Corré con:  .venv/bin/python -m rinthel_tui.daemon   (o el entry point
``rinthel-daemon``, ver pyproject.toml)
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable
from datetime import datetime

from fastapi import FastAPI

from rinthel_tui import database
from rinthel_tui.api import create_app
from rinthel_tui.code_version import running_code_version
from rinthel_tui.config import RinthelConfig, default_config
from rinthel_tui.identity.adapters.sqlite import SqliteIdentity
from rinthel_tui.instance import Instance


def startup_line(now: datetime, pid: int, version: str) -> str:
    """Marca de inicio de un boot en ``daemon.log`` (que se anexa, sin rotar):
    fecha ISO, PID y huella del código."""
    return f"[daemon] inicio {now.isoformat(timespec='seconds')} pid={pid} codigo={version}"


def open_identity(instance: Instance) -> None:
    """Startup gate of ``rinthel.db`` (ADR 0007), before the app exists:
    migrates it, or stops the daemon with a clear error if SQLite is older
    than 3.37 or the file has a schema newer than this code. Without an
    active admin it warns: Deck still requires login and there is no open
    mode, so the operator has to run ``reset-admin``."""
    path = instance.database_path
    try:
        database.migrate(path)
    except database.DatabaseError as exc:
        print(f"[daemon] error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    if not SqliteIdentity(path).has_admin():
        print(
            "[daemon] aviso: sin admin activo: corré reset-admin "
            "(python -m rinthel_tui.identity reset-admin)",
            file=sys.stderr,
        )


def main() -> None:
    instance = Instance.discover()
    run(instance, default_config(instance))


def run(instance: Instance, cfg: RinthelConfig, *, create_app: Callable[..., FastAPI] = create_app) -> None:
    """App y servidor. ``main`` solo descubre la Instance y su config;
    ``create_app`` es un parámetro para que un test llegue (o no) a construir
    la app sin parchear el módulo."""
    import uvicorn

    print(startup_line(datetime.now().astimezone(), os.getpid(), running_code_version()), flush=True)
    if not cfg.secrets.service:
        print(
            "[daemon] aviso: RINTHEL_SERVICE_SECRET vacío — la TUI no va a poder entrar; "
            "corré rinthel-boot.sh (lo genera) o [0] INSTALL",
            file=sys.stderr,
        )
    if cfg.model_warning:
        print(f"[daemon] aviso: {cfg.model_warning} — llama-server no arranca", file=sys.stderr)
    open_identity(instance)
    # `/docs` y `/redoc` solo en desarrollo: con el flag, esas dos y
    # `/openapi.json` son públicas. Mismo override que el puerto.
    docs = (instance.variable("RINTHEL_DAEMON_DOCS") or "").strip() == "1"
    app = create_app(cfg, docs=docs)

    # Puerto propio del daemon (distinto de los servicios reales) —
    # overrideable por `.env`; `rinthel-boot.sh` lo lee de ahí y se lo pasa
    # al binario Rust como `--port`, default 8765 si nadie lo setea.
    port = int(instance.variable("RINTHEL_DAEMON_PORT") or "8765")
    print(f"[daemon] {time.strftime('%H:%M:%S')} arrancando en http://127.0.0.1:{port}")
    print(f"[daemon] tail real de: {cfg.llama.log}")
    # workers=1 a propósito, no el default implícito de uvicorn:
    # `app.state.cfg` y los clientes de `/ws/monitor` son estado mutable en
    # memoria sin lock (`POST /config` reemplaza `app.state.cfg`). Con más de
    # un worker cada proceso vería su propia copia de `cfg` tras un
    # POST /config — Rinthel es monousuario, no hace falta más de uno.
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning", workers=1)


if __name__ == "__main__":
    main()
