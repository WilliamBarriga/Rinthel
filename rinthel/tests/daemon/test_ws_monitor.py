"""Handshake de ``/ws/monitor`` bajo la policy ``service``: el secreto viaja
en ``?token=`` y sin él el handshake se rechaza con 4401 antes de
``accept()``."""

import dataclasses

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from rinthel_tui.api import create_app
from rinthel_tui.config import Secrets


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


@pytest.mark.parametrize("ready", [True, False])
def test_the_monitor_streams_whether_llama_server_is_ready(client, telemetry, service_headers, ready):
    telemetry.llama.is_ready = ready
    token = service_headers["x-rinthel-service-secret"]

    with client.websocket_connect(f"/ws/monitor?token={token}") as ws:
        while (message := ws.receive_json())["type"] != "llama_status":
            pass

    assert message == {"type": "llama_status", "data": {"ready": ready}}
