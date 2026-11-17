"""Handshake de ``/ws/monitor`` bajo la policy ``service``: el secreto viaja
en ``?token=`` y sin él el handshake se rechaza con 4401 antes de
``accept()``."""

import dataclasses

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from rinthel_tui.api import create_app
from rinthel_tui.config import Secrets
from rinthel_tui.monitoring.domain.types import CapabilityStatus, ModelsStatus, ServiceStatus


@pytest.mark.parametrize("query", ["", "?token=", "?token=wrong"])
def test_handshake_without_a_valid_token_is_rejected_with_4401(client, query):
    with pytest.raises(WebSocketDisconnect) as closed, client.websocket_connect(f"/ws/monitor{query}"):
        pass
    assert closed.value.code == 4401


def test_empty_configured_secret_rejects_every_handshake(daemon_cfg, adapters):
    cfg = dataclasses.replace(daemon_cfg, secrets=Secrets(service="", panel=""))
    app = create_app(cfg, adapters=adapters)
    with pytest.raises(WebSocketDisconnect) as closed, TestClient(app).websocket_connect("/ws/monitor?token="):
        pass
    assert closed.value.code == 4401


def test_valid_token_receives_messages_in_the_type_data_envelope(client, service_headers):
    token = service_headers["x-rinthel-service-secret"]
    with client.websocket_connect(f"/ws/monitor?token={token}") as ws:
        message = ws.receive_json()
    assert message.keys() == {"type", "data"}
    assert isinstance(message["type"], str)
    assert isinstance(message["data"], dict)


def test_the_monitor_streams_the_models_status(client, telemetry, service_headers):
    telemetry.models.status = ModelsStatus(
        capabilities=[CapabilityStatus("llm", "qwen", "ready")], services=[ServiceStatus("Understory", "down")]
    )
    token = service_headers["x-rinthel-service-secret"]

    with client.websocket_connect(f"/ws/monitor?token={token}") as ws:
        while (message := ws.receive_json())["type"] != "models_status":
            pass

    assert message == {"type": "models_status", "data": {
        "capabilities": [{"capability": "llm", "model": "qwen", "state": "ready", "error": None}],
        "services": [{"name": "Understory", "state": "down"}],
    }}
