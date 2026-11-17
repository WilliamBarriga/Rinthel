"""La composición del Monitor de ``/ws/monitor``: la telemetría de la Instance en un solo flujo."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter

from rinthel_tui.api.adapters import Adapters
from rinthel_tui.api.shared import Shared
from rinthel_tui.api.ws.routes import router
from rinthel_tui.monitoring.domain.monitor import Monitor, streams


@dataclass(frozen=True)
class WsArea:
    monitor: Monitor
    router: APIRouter


def compose(adapters: Adapters, shared: Shared) -> WsArea:
    monitor = Monitor(streams(adapters.telemetry, clock=shared.clock), clock=shared.clock)
    return WsArea(monitor=monitor, router=router)
