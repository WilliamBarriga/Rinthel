"""Contract of the ``DeckSessions`` port: the in-memory double and the HTTP
adapter against a stub Deck that speaks ``POST /api/agent/retire-sessions``
(service secret + ``X-Rinthel-User-Id``, answer ``{"retired": n}``)."""

import json
import socket
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler

import httpx
import pytest

from rinthel_tui.identity.adapters.deck_http import HttpDeckSessions
from rinthel_tui.identity.adapters.memory import InMemoryDeckSessions
from rinthel_tui.identity.domain.errors import DeckSessionsError

SECRET = "deck-test-secret"


@dataclass
class Deck:
    """A port under test plus the knobs of the Deck behind it."""

    port: object
    add: object  # owner_id -> None
    refuse: object  # () -> None
    go_down: object  # () -> None


def _stub_deck(sessions: dict[int, int], state: dict) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers.get("content-length") or 0))
            if state["status"] != 200:
                return self._answer(state["status"], {"error": "x"})
            if self.path != "/api/agent/retire-sessions" or self.headers.get("x-rinthel-service-secret") != SECRET:
                return self._answer(401, {"error": "unauthorized"})
            owner = int(self.headers["x-rinthel-user-id"])
            retired = sessions.pop(owner, 0)
            self._answer(200, {"retired": retired})

        def _answer(self, status, body):
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return Handler


def _closed_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(params=["memory", "http"])
def deck(request, serve_http):
    if request.param == "memory":
        fake = InMemoryDeckSessions()

        def down():
            fake.fail_next("retire_user_sessions", DeckSessionsError("deck unreachable"))

        yield Deck(fake, fake.add, lambda: setattr(fake, "refuse", True), down)
        return
    sessions: dict[int, int] = {}
    state = {"status": 200}
    port = serve_http(_stub_deck(sessions, state))
    holder = {"url": f"http://127.0.0.1:{port}"}

    def adapter_call(user_id: int) -> int:
        with httpx.Client(base_url=holder["url"], timeout=2) as client:
            return HttpDeckSessions(client, service_secret=SECRET).retire_user_sessions(user_id)

    class Port:
        retire_user_sessions = staticmethod(adapter_call)

    def add(owner: int) -> None:
        sessions[owner] = sessions.get(owner, 0) + 1

    def refuse() -> None:
        state["status"] = 401

    def down() -> None:
        holder["url"] = f"http://127.0.0.1:{_closed_port()}"

    yield Deck(Port(), add, refuse, down)


def test_retiring_returns_how_many_sessions_the_user_had(deck):
    deck.add(7)
    deck.add(7)
    deck.add(8)

    assert deck.port.retire_user_sessions(7) == 2


def test_retiring_is_idempotent(deck):
    deck.add(7)
    deck.port.retire_user_sessions(7)

    assert deck.port.retire_user_sessions(7) == 0


def test_a_refusal_is_an_error(deck):
    deck.refuse()

    with pytest.raises(DeckSessionsError):
        deck.port.retire_user_sessions(7)


def test_a_deck_that_does_not_answer_is_an_error(deck):
    deck.go_down()

    with pytest.raises(DeckSessionsError):
        deck.port.retire_user_sessions(7)
