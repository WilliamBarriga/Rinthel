"""Deck in the daemon's composition: ``Adapters.from_cfg`` wires the real
``DeckSessions`` to Deck's address (``cfg.deck.port`` on the host loopback)
with the Instance's service secret, so deleting a user over HTTP retires the
user's Sessions in Deck first. A disabled Deck has no Sessions to retire.
Deck here is a stub HTTP server; the rest is ``create_app`` on a temporary
root."""

import json
from dataclasses import replace
from http.server import BaseHTTPRequestHandler

from fastapi.testclient import TestClient

from rinthel_tui.api import create_app
from rinthel_tui.api.adapters import Adapters
from tests.daemon.conftest import SERVICE_SECRET

PASSWORD = "pw123456"


def _stub_deck(calls: list, status: int = 200):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers.get("content-length") or 0))
            calls.append((self.path, self.headers.get("x-rinthel-service-secret"), self.headers.get("x-rinthel-user-id")))
            data = json.dumps({"retired": 1} if status == 200 else {"error": "x"}).encode()
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return Handler


def _app(cfg, adapters):
    """The daemon with the real Deck wiring of ``from_cfg`` and the test's other adapters."""
    real = Adapters.from_cfg(cfg_of=lambda: cfg)
    return TestClient(create_app(cfg, adapters=replace(adapters, deck_sessions=real.deck_sessions)))


def _admin_bearer(client) -> dict:
    token = client.post("/identity/login", json={"username": "admin", "password": PASSWORD}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_deck_defaults_to_its_own_port_next_to_the_legacy_portal(daemon_cfg):
    assert daemon_cfg.deck.enabled is True
    assert daemon_cfg.deck.port == 4200
    assert daemon_cfg.deck.port != daemon_cfg.pithagoras.port


def test_deleting_a_user_asks_the_configured_deck_to_retire_their_sessions(
    daemon_cfg, adapters, seed_user, identity, serve_http
):
    calls: list = []
    cfg = replace(daemon_cfg, deck=replace(daemon_cfg.deck, port=serve_http(_stub_deck(calls))))
    client = _app(cfg, adapters)
    seed_user("admin", role="admin")
    ana = seed_user("ana")

    response = client.delete(f"/identity/users/{ana.id}", headers=_admin_bearer(client))

    assert (response.status_code, response.json()) == (200, {"ok": True})
    assert calls == [("/api/agent/retire-sessions", SERVICE_SECRET, str(ana.id))]
    assert identity.get_user(ana.id) is None


def test_if_the_configured_deck_refuses_the_user_stays(daemon_cfg, adapters, seed_user, identity, serve_http):
    calls: list = []
    cfg = replace(daemon_cfg, deck=replace(daemon_cfg.deck, port=serve_http(_stub_deck(calls, status=500))))
    client = _app(cfg, adapters)
    seed_user("admin", role="admin")
    ana = seed_user("ana")

    response = client.delete(f"/identity/users/{ana.id}", headers=_admin_bearer(client))

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "sessions_not_retired"
    assert identity.get_user(ana.id) is not None


def test_a_disabled_deck_is_not_called(daemon_cfg, adapters, seed_user, identity, serve_http):
    calls: list = []
    port = serve_http(_stub_deck(calls))
    cfg = replace(daemon_cfg, deck=replace(daemon_cfg.deck, port=port, enabled=False))
    client = _app(cfg, adapters)
    seed_user("admin", role="admin")
    ana = seed_user("ana")

    assert client.delete(f"/identity/users/{ana.id}", headers=_admin_bearer(client)).status_code == 200
    assert calls == []
    assert identity.get_user(ana.id) is None
