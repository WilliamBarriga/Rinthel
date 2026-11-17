"""Adapter WS de entrada: ``/ws/monitor`` multiplexa, con un sobre
``{"type", "data"}`` por mensaje, la telemetría que produce el Monitor
(``app.state.monitor``, dominio de ``monitoring/``; un flujo por
cliente: ``docker_status``, ``gpu_sample``, ``cpu_ram_sample``,
``log_line``, ``llama_status``) y el progreso de una corrida en curso
(``phase_status``, ``phase_log``, ``phase_batch``). Todo esto es best-effort:
``Broadcaster.broadcast`` descarta el cliente que no recibe, y perder un
mensaje de progreso no afecta el ``ServiceOutcome`` final que viaja por la
respuesta del POST. El progreso de una corrida lo emite
``lifecycle/executor.py``, en orden (se awaitea). ``phase_batch``
(``{"batch": "boot"|"rebuild"}``) marca el límite entre tandas de
``/reload`` — el cliente lo usa para disparar sus transiciones visuales
entre tandas."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from rinthel_tui.api import access
from rinthel_tui.monitoring.domain.envelope import MessageType, envelope
from rinthel_tui.monitoring.domain.monitor import Monitor

router = APIRouter()


class Broadcaster:
    """Clientes ``/ws/monitor`` conectados ahora mismo — Rinthel es
    monousuario así que en la práctica hay 0 o 1, pero el set soporta más
    sin cambios. Sin cliente conectado, ``broadcast`` es un no-op."""

    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()

    async def broadcast(self, type_: MessageType, data: dict) -> None:
        dead = []
        for ws in list(self.clients):  # connect/disconnect durante el await
            try:
                await ws.send_text(envelope(type_, data))
            except Exception:  # noqa: BLE001 — cualquier fallo de envío = cliente muerto, el broadcast sigue con el resto
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)


@router.websocket("/ws/monitor", dependencies=[Depends(access.service)])
async def ws_monitor(ws: WebSocket) -> None:
    await ws.accept()
    broadcaster: Broadcaster = ws.app.state.broadcaster
    monitor: Monitor = ws.app.state.monitor
    broadcaster.clients.add(ws)

    async def pump() -> None:
        async for message in monitor.stream():
            await ws.send_text(message)

    task = asyncio.create_task(pump())
    try:
        while True:
            await ws.receive_text()  # el cliente no manda nada; solo detecta disconnect
    except WebSocketDisconnect:
        pass
    finally:
        broadcaster.clients.discard(ws)
        task.cancel()
