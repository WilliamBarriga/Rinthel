"""Suite de contrato del puerto ``Probe``: sockets y un ``http.server`` locales
contra ``FakeProbe``. Un puerto sin nadie, una URL que rechaza o que
responde 5xx son ``False``, nunca una excepción."""

import socket
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from rinthel_tui.lifecycle.adapters.socket_probe import SocketProbe
from tests.lifecycle.fakes import FakeProbe


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200 if self.path == "/ok" else 500)
        self.end_headers()

    def log_message(self, *args):
        pass


@dataclass
class World:
    probe: object
    port_open: int
    port_closed: int
    url_ok: str
    url_500: str
    url_down: str


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(params=["socket", "fake"])
def world(request):
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    down = _free_port()
    world = World(
        probe=None, port_open=server.server_port, port_closed=down,
        url_ok=f"{base}/ok", url_500=f"{base}/boom", url_down=f"http://127.0.0.1:{down}/",
    )
    if request.param == "socket":
        world.probe = SocketProbe()
    else:
        fake = FakeProbe()
        fake.script_port(world.port_open, True)
        fake.script_http(world.url_ok, True)
        world.probe = fake
    yield world
    server.shutdown()
    server.server_close()


async def test_a_listening_port_is_open(world):
    assert await world.probe.port_open(world.port_open) is True


async def test_a_port_nobody_listens_on_is_closed(world):
    assert await world.probe.port_open(world.port_closed) is False


async def test_a_url_that_answers_200_is_ok(world):
    assert await world.probe.http_ok(world.url_ok) is True


async def test_a_url_that_answers_500_is_not_ok(world):
    assert await world.probe.http_ok(world.url_500) is False


async def test_a_url_that_refuses_the_connection_is_not_ok(world):
    assert await world.probe.http_ok(world.url_down, timeout=1) is False


async def test_a_fake_answers_in_batches_and_keeps_the_last_one():
    fake = FakeProbe()
    fake.script_port(8080, [True, True, False])

    answers = [await fake.port_open(8080) for _ in range(5)]

    assert answers == [True, True, False, False, False]
