"""``python -m rinthel_tui.install [--voice]``: asks the running daemon for
INSTALL (``POST /install``) with the Instance's service secret and prints one
line per unit. A local HTTP server plays the daemon."""

import json
from http.server import BaseHTTPRequestHandler

import pytest

from rinthel_tui.install.__main__ import main
from rinthel_tui.instance import Instance


class Daemon(BaseHTTPRequestHandler):
    requests: list[tuple[str, str | None, dict]] = []
    results: list[dict] = [{"service": "voz", "ok": True, "message": "whisper-server respondiendo"}]

    def do_POST(self):
        length = int(self.headers.get("content-length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        Daemon.requests.append((self.path, self.headers.get("x-rinthel-service-secret"), body))
        payload = json.dumps({"results": Daemon.results}).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


@pytest.fixture
def instance(tmp_path, serve_http, monkeypatch):
    monkeypatch.delenv("RINTHEL_DAEMON_PORT", raising=False)
    Daemon.requests = []
    port = serve_http(Daemon)
    instance = Instance(tmp_path)
    instance.env_path.write_text(f"RINTHEL_DAEMON_PORT={port}\nRINTHEL_SERVICE_SECRET=s3cret\n")
    return instance


def test_voice_asks_the_daemon_for_install_with_voice(instance, capsys):
    assert main(["--root", str(instance.root), "--voice"]) == 0

    assert Daemon.requests == [("/install", "s3cret", {"voice": True})]
    assert "voz" in capsys.readouterr().out


def test_without_voice_it_is_the_plain_install(instance):
    main(["--root", str(instance.root)])

    assert Daemon.requests == [("/install", "s3cret", {"voice": False})]


def test_a_failed_unit_is_a_failed_command(instance, capsys):
    Daemon.results = [{"service": "voz", "ok": False, "message": "nvcc no encontrado"}]
    try:
        assert main(["--root", str(instance.root), "--voice"]) == 1
    finally:
        Daemon.results = [{"service": "voz", "ok": True, "message": "ok"}]
    assert "nvcc" in capsys.readouterr().out


def test_without_a_running_daemon_it_says_so(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("RINTHEL_DAEMON_PORT", raising=False)
    Instance(tmp_path).env_path.write_text("RINTHEL_DAEMON_PORT=1\nRINTHEL_SERVICE_SECRET=x\n")

    assert main(["--root", str(tmp_path), "--voice"]) == 2
    assert "daemon" in capsys.readouterr().err
