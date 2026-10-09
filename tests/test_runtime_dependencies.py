"""Dependencias necesarias en runtime, no solo para importar el paquete."""

import importlib.util


def test_websocket_transport_is_installed():
    """Uvicorn necesita un transporte WS para servir ``/ws/monitor``."""
    assert importlib.util.find_spec("websockets") is not None
