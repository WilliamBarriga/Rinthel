"""Suite de contrato del puerto ``ServiceReadiness``: ``HttpReadiness`` contra
un ``http.server`` local (con el ``SocketProbe`` real que le da la
composición) y ``InMemoryReadiness`` pasan lo mismo."""

from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler

import pytest

from rinthel_tui.lifecycle.adapters.socket_probe import SocketProbe
from rinthel_tui.monitoring.adapters.http_readiness import HttpReadiness
from rinthel_tui.monitoring.adapters.memory import InMemoryReadiness


class _Ready(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200 if self.path == "/v1/models" else 503)
        self.end_headers()

    def log_message(self, *args):
        pass


@dataclass
class World:
    up: object  # () -> ServiceReadiness de un servicio que responde
    down: object  # () -> ServiceReadiness de un servicio que no


@pytest.fixture(params=["http", "memory"])
def world(request, serve_http):
    if request.param == "memory":
        return World(lambda: InMemoryReadiness(True), lambda: InMemoryReadiness(False))
    port = serve_http(_Ready)
    probe = SocketProbe()
    return World(
        lambda: HttpReadiness(lambda: f"http://127.0.0.1:{port}/v1/models", probe.http_ok),
        lambda: HttpReadiness(lambda: f"http://127.0.0.1:{port}/loading", probe.http_ok),
    )


async def test_a_service_that_answers_is_ready(world):
    assert await world.up().ready() is True


async def test_a_service_that_does_not_answer_yet_is_not_ready(world):
    assert await world.down().ready() is False


async def test_nothing_listening_is_not_ready():
    probe = SocketProbe()
    assert await HttpReadiness(lambda: "http://127.0.0.1:9/v1/models", probe.http_ok).ready() is False
