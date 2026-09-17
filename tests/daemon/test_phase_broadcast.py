"""``daemon.broadcast``/``daemon._ws_clients`` — el fan-out genérico de
``/ws/monitor``. La emisión de ``phase_status``/``phase_log`` en sí (quién
llama a ``broadcast`` y con qué payload) vive en ``phase_bridge.run_unit`` y
se prueba en ``tests/test_phase_bridge.py``, inyectando una función de
prueba en vez de monkeypatchear esta."""

from rinthel_tui import daemon


async def test_broadcast_is_noop_with_no_connected_clients():
    daemon._ws_clients.clear()
    await daemon.broadcast("phase_status", {"label": "x", "status": "running"})  # no debe levantar
