"""La app HTTP del daemon: ``create_app(cfg)`` la arma con un router por
área y deja ``cfg`` en ``app.state`` — sin global. ``daemon.main()`` es el
único que la construye en producción; los tests la construyen con su propio
``cfg`` (ver ``tests/daemon/conftest.py``)."""

from __future__ import annotations

from fastapi import FastAPI

from rinthel_tui.api import config, identity, lifecycle, models, openapi, secrets, ws
from rinthel_tui.api.adapters import Adapters
from rinthel_tui.api.errors import install_errors
from rinthel_tui.api.shared import Shared
from rinthel_tui.api.ws import Broadcaster
from rinthel_tui.config import RinthelConfig
from rinthel_tui.lifecycle.commands import LifecycleLock


def create_app(cfg: RinthelConfig, *, docs: bool = False, adapters: Adapters | None = None) -> FastAPI:
    """``docs`` (``RINTHEL_DAEMON_DOCS=1``) monta ``/docs`` y ``/redoc`` y
    vuelve públicas esas dos y ``/openapi.json`` — ver ``openapi.mount_docs``.
    Es el único lugar que elige los adapters (ADR 0004): ``adapters`` o,
    sin él, los reales de ``cfg``."""
    app = FastAPI(
        title="Rinthel Daemon",
        version="0.1.0",
        description=(
            "Daemon FastAPI para gestionar el ciclo de vida de llama-server, "
            "Understory y el portal. Expone endpoints de lifecycle (boot, "
            "terminate, reload, install), configuración, rotación de secretos "
            "y el Monitor por WebSocket."
        ),
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.cfg = cfg
    broadcaster = Broadcaster()
    app.state.broadcaster = broadcaster

    def live_cfg() -> RinthelConfig:
        """El ``cfg`` vigente: ``POST /config`` y ``POST /secrets/rotate``
        reemplazan ``app.state.cfg``, y quien lo pide (la telemetría) lo
        necesita al día en cada muestra."""
        return app.state.cfg

    adapters = adapters or Adapters.from_cfg(cfg_of=live_cfg)
    app.state.clock = adapters.clock
    app.state.lifecycle_host = adapters.lifecycle_host
    shared = Shared(cfg=cfg, clock=adapters.clock)

    # El orden de armado, explícito; cada área construye sus módulos en su
    # ``compose`` y ``create_app`` solo las encadena.
    ws_area = ws.compose(adapters, shared)
    app.state.monitor = ws_area.monitor
    identity_area = identity.compose(adapters)
    app.state.identity = identity_area.identity
    app.state.deck_sessions = identity_area.deck_sessions
    # Boot, terminate, reload, install y el cambio de Local model se excluyen.
    app.state.lifecycle_lock = LifecycleLock()

    def set_cfg(updated: RinthelConfig) -> None:
        app.state.cfg = updated

    models_area = models.compose(adapters, cfg_of=live_cfg, set_cfg=set_cfg, broadcast=broadcaster.broadcast)
    app.state.models = models_area
    routers = (config.router, ws_area.router, lifecycle.router, secrets.router, identity_area.router, models_area.router)
    for router in routers:
        app.include_router(router)
    install_errors(app, identity_area.errors)
    openapi.install_security_schemes(app)
    openapi.mount_docs(app, public=docs)
    return app
