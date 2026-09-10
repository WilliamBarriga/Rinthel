"""Ejemplo de la categoría 'services/tts-piper' — wrapper HTTP sobre piper.

`services/tts-piper/server.py` vive fuera del paquete `rinthel_tui` (no es
importable por nombre por el guion en `tts-piper/`), así que se carga por
path con importlib. Estilo de mocking: se reemplaza `subprocess.run` (todo
lo que `_synthesize` usa para invocar el binario real) y el servidor HTTP en
sí se levanta real en un puerto efímero de loopback, para probar el
parseo de request/response tal cual lo ve un cliente.
"""

import contextlib
import http.client
import importlib.util
import json
import subprocess
import threading
from pathlib import Path

import pytest

_SERVER_PATH = Path(__file__).resolve().parent.parent / "services" / "tts-piper" / "server.py"

_TOKEN = "test-token"
_AUTH_HEADER = {"Authorization": f"Bearer {_TOKEN}"}


def _load_server_module():
    spec = importlib.util.spec_from_file_location("tts_piper_server", _SERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tts_server = _load_server_module()


@contextlib.contextmanager
def _server(**handler_kwargs):
    voices = handler_kwargs.pop("voices", {"es": "voice-es.onnx", "en": "voice-en.onnx"})
    piper_bin = handler_kwargs.pop("piper_bin", "piper-bin")
    handler_kwargs.setdefault("auth_token", _TOKEN)
    handler_cls = tts_server.make_handler(voices, piper_bin, **handler_kwargs)
    server = tts_server.ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


@pytest.fixture
def running_server(monkeypatch):
    def fake_run(argv, input=None, capture_output=None, check=None):
        out_path = argv[argv.index("--output_file") + 1]
        Path(out_path).write_bytes(b"RIFF....WAVEfake")
        return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with _server() as server:
        yield server


def test_speak_returns_wav_for_valid_payload(running_server):
    port = running_server.server_address[1]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    body = json.dumps({"text": "hola", "lang": "es"}).encode()
    conn.request("POST", "/speak", body=body, headers={"Content-Length": str(len(body)), **_AUTH_HEADER})
    resp = conn.getresponse()
    data = resp.read()
    conn.close()

    assert resp.status == 200
    assert resp.getheader("Content-Type") == "audio/wav"
    assert data == b"RIFF....WAVEfake"


def test_speak_rejects_malformed_json(running_server):
    port = running_server.server_address[1]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    body = b"not json"
    conn.request("POST", "/speak", body=body, headers={"Content-Length": str(len(body)), **_AUTH_HEADER})
    resp = conn.getresponse()
    resp.read()
    conn.close()

    assert resp.status == 400


def test_speak_falls_back_to_spanish_voice_for_unknown_lang(monkeypatch, running_server):
    used_voice = {}

    def fake_run(argv, input=None, capture_output=None, check=None):
        used_voice["path"] = argv[argv.index("--model") + 1]
        out_path = argv[argv.index("--output_file") + 1]
        Path(out_path).write_bytes(b"fake")
        return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(subprocess, "run", fake_run)

    port = running_server.server_address[1]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    body = json.dumps({"text": "bonjour", "lang": "fr"}).encode()
    conn.request("POST", "/speak", body=body, headers={"Content-Length": str(len(body)), **_AUTH_HEADER})
    resp = conn.getresponse()
    resp.read()
    conn.close()

    assert resp.status == 200
    assert used_voice["path"] == "voice-es.onnx"


def test_speak_returns_500_when_piper_fails(monkeypatch, running_server):
    def fake_run(argv, input=None, capture_output=None, check=None):
        raise subprocess.CalledProcessError(1, argv, stderr=b"piper blew up")

    monkeypatch.setattr(subprocess, "run", fake_run)

    port = running_server.server_address[1]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    body = json.dumps({"text": "hola"}).encode()
    conn.request("POST", "/speak", body=body, headers={"Content-Length": str(len(body)), **_AUTH_HEADER})
    resp = conn.getresponse()
    data = resp.read()
    conn.close()

    assert resp.status == 500
    assert b"piper blew up" in data


def test_speak_rejects_missing_token(running_server):
    port = running_server.server_address[1]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    body = json.dumps({"text": "hola"}).encode()
    conn.request("POST", "/speak", body=body, headers={"Content-Length": str(len(body))})
    resp = conn.getresponse()
    resp.read()
    conn.close()

    assert resp.status == 401


def test_speak_rejects_wrong_token(running_server):
    port = running_server.server_address[1]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    body = json.dumps({"text": "hola"}).encode()
    conn.request(
        "POST", "/speak", body=body,
        headers={"Content-Length": str(len(body)), "Authorization": "Bearer wrong-token"},
    )
    resp = conn.getresponse()
    resp.read()
    conn.close()

    assert resp.status == 401


def test_speak_rejects_mismatched_origin(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess([], 0))

    with _server(allowed_origin="http://trusted.local") as server:
        port = server.server_address[1]
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        body = json.dumps({"text": "hola"}).encode()
        conn.request(
            "POST", "/speak", body=body,
            headers={"Content-Length": str(len(body)), "Origin": "http://evil.example", **_AUTH_HEADER},
        )
        resp = conn.getresponse()
        resp.read()
        conn.close()

        assert resp.status == 403


def test_speak_rejects_text_over_max_length():
    with _server(max_text_length=5) as server:
        port = server.server_address[1]
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        body = json.dumps({"text": "esto es demasiado largo"}).encode()
        conn.request("POST", "/speak", body=body, headers={"Content-Length": str(len(body)), **_AUTH_HEADER})
        resp = conn.getresponse()
        resp.read()
        conn.close()

        assert resp.status == 413


def test_health_check_does_not_require_auth(running_server):
    port = running_server.server_address[1]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", "/")
    resp = conn.getresponse()
    data = resp.read()
    conn.close()

    assert resp.status == 200
    assert data == b"tts-piper ok"


def test_options_returns_cors_preflight_headers():
    with _server(allowed_origin="http://trusted.local") as server:
        port = server.server_address[1]
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("OPTIONS", "/speak")
        resp = conn.getresponse()
        resp.read()
        conn.close()

        assert resp.status == 204
        assert resp.getheader("Access-Control-Allow-Origin") == "http://trusted.local"
