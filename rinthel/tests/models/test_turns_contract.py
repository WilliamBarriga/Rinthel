"""Suite de contrato del puerto ``Turns``: ``GET /slots`` de llama-server
(``LlamaSlotsTurns``, contra un ``http.server`` local) y el doble en memoria."""

import json
from http.server import BaseHTTPRequestHandler

import pytest

from rinthel_tui.models.adapters.llama_slots import LlamaSlotsTurns
from rinthel_tui.models.adapters.memory import InMemoryTurns


def _slots_server(serve_http, processing: list[bool]) -> str:
    class Slots(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps([{"id": i, "is_processing": p} for i, p in enumerate(processing)]).encode()
            self.send_response(200 if self.path == "/slots" else 404)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    return f"http://127.0.0.1:{serve_http(Slots)}"


@pytest.fixture(params=["llama", "memory"])
def turns_with(request, serve_http):
    """``turns_with(busy)``: el puerto con un turno en curso o sin ninguno."""

    def make(busy: bool):
        if request.param == "memory":
            return InMemoryTurns(busy)
        url = _slots_server(serve_http, [False, busy])
        return LlamaSlotsTurns(lambda: url)

    return make


async def test_no_turn_in_flight_when_every_slot_is_idle(turns_with):
    assert await turns_with(False).in_flight() is False


async def test_a_processing_slot_is_a_turn_in_flight(turns_with):
    assert await turns_with(True).in_flight() is True


async def test_a_llama_server_that_does_not_answer_generates_nothing():
    assert await LlamaSlotsTurns(lambda: "http://127.0.0.1:1", timeout=0.5).in_flight() is False
